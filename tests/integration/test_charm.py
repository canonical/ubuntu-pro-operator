# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import os
import pathlib

import jubilant
import pytest

# The packed charm under test, e.g. ubuntu-pro_ubuntu-24.04-amd64.charm.
CHARM_PATH = os.environ.get("CHARM_PATH")
assert CHARM_PATH is not None
CHARM_PATH = pathlib.Path(CHARM_PATH).resolve()
# Packed charm file names start with the charm name.
APP = CHARM_PATH.name.split("_")[0]
UNIT = f"{APP}/0"

# The base both the principal and the subordinate are deployed on, e.g. "ubuntu@24.04".
# It must be one of the bases the charm supports.
TEST_BASE = os.environ.get("PRO_CHARM_TEST_BASE")
assert TEST_BASE is not None

TEST_TOKEN = os.environ.get("PRO_CHARM_TEST_TOKEN")
assert TEST_TOKEN is not None
# Optional: tests that need a real Livepatch staging token are skipped without one.
TEST_LIVEPATCH_TOKEN = os.environ.get("PRO_CHARM_TEST_LIVEPATCH_STAGING_TOKEN")

NO_TOKEN_MESSAGE = "No token configured"


@pytest.fixture(scope="module")
def juju(juju: jubilant.Juju):
    # Deploying and attaching can take longer than Jubilant's 3-minute default.
    juju.wait_timeout = 10 * 60
    return juju


def unit_status(status: jubilant.Status) -> jubilant.statustypes.UnitStatus:
    return status.get_units(APP)[UNIT]


def wait_active(juju: jubilant.Juju) -> jubilant.statustypes.UnitStatus:
    return unit_status(juju.wait(lambda s: jubilant.all_active(s, APP), error=jubilant.any_error))


def wait_blocked(juju: jubilant.Juju) -> jubilant.statustypes.UnitStatus:
    return unit_status(juju.wait(lambda s: jubilant.all_blocked(s, APP), error=jubilant.any_error))


def wait_blocked_on_error(juju: jubilant.Juju) -> jubilant.statustypes.UnitStatus:
    """Wait for an already-blocked unit to replace the "no token" message with an error."""

    def ready(status: jubilant.Status) -> bool:
        unit = unit_status(status)
        return unit.is_blocked and unit.workload_status.message != NO_TOKEN_MESSAGE

    return unit_status(juju.wait(ready, error=jubilant.any_error))


def pro_config(juju: jubilant.Juju) -> str:
    return juju.exec("pro config show", unit=UNIT).stdout


@pytest.mark.juju_setup
def test_deploy(juju: jubilant.Juju):
    juju.deploy("ubuntu", base=TEST_BASE)
    juju.deploy(CHARM_PATH, APP, base=TEST_BASE)
    juju.integrate("ubuntu", APP)
    juju.wait(
        lambda s: jubilant.all_active(s, "ubuntu") and jubilant.all_blocked(s, APP),
        error=jubilant.any_error,
    )


def test_status(juju: jubilant.Juju):
    status = juju.status()
    assert status.apps["ubuntu"].is_active
    assert status.apps[APP].is_blocked


def test_attach_invalid_token(juju: jubilant.Juju):
    juju.config(APP, {"token": ""})
    wait_blocked(juju)

    juju.config(APP, {"token": "new-token-2"})
    unit = wait_blocked_on_error(juju)

    expected_error = "stderr: Invalid token."
    assert expected_error in unit.workload_status.message
    assert "new-token-2" not in unit.workload_status.message


def test_attach_default_services(juju: jubilant.Juju):
    # Attach to pro subscription without specifying services
    juju.config(APP, {"token": TEST_TOKEN})
    unit = wait_active(juju)
    assert unit.workload_status.message == "Attached (esm-apps,esm-infra)"

    # Detach from pro subscription
    juju.config(APP, {"token": ""})
    wait_blocked(juju)


def test_attach_services(juju: jubilant.Juju):
    # Attach with an explicit services list, "esm-infra" alone still differs from the default
    # (esm-apps,esm-infra), so it proves the override is applied.
    juju.config(APP, {"services": "esm-infra", "token": TEST_TOKEN})
    unit = wait_active(juju)
    assert unit.workload_status.message == "Attached (esm-infra)"

    # Detach from pro subscription
    juju.config(APP, {"token": "", "services": ""})
    wait_blocked(juju)


def test_detach_before_attach(juju: jubilant.Juju):
    # Attach to pro subscription with services "manually" to get the unit
    # in a weird state to test the detach before attach logic.
    juju.exec(f"sudo pro attach {TEST_TOKEN} --no-auto-enable", unit=UNIT)
    task = juju.exec("sudo pro api u.pro.status.is_attached.v1", unit=UNIT)
    assert json.loads(task.stdout)["data"]["attributes"]["is_attached"] is True

    # Attach to pro subscription with services
    # This will detach the existing attachment and then attach.
    # We will know the second attachment succeeded because it will enable esm-infra.
    juju.config(APP, {"services": "esm-infra", "token": TEST_TOKEN})
    unit = wait_active(juju)
    assert unit.workload_status.message == "Attached (esm-infra)"

    # Detach from pro subscription
    juju.config(APP, {"token": "", "services": ""})
    wait_blocked(juju)


def test_empty_livepatch_config(juju: jubilant.Juju):
    juju.config(APP, {"token": TEST_TOKEN, "livepatch_token": ""})
    wait_active(juju)

    # Detach from pro subscription
    juju.config(APP, {"token": ""})
    wait_blocked(juju)


@pytest.mark.skipif(
    not TEST_LIVEPATCH_TOKEN, reason="PRO_CHARM_TEST_LIVEPATCH_STAGING_TOKEN is not set"
)
def test_livepatch_server_success(juju: jubilant.Juju):
    juju.config(
        APP,
        {
            "livepatch_server_url": "https://livepatch.staging.canonical.com",
            "livepatch_token": TEST_LIVEPATCH_TOKEN,
            "token": TEST_TOKEN,
        },
    )
    wait_active(juju)

    # Detach from pro subscription and livepatch
    juju.config(APP, {"token": "", "livepatch_token": "", "livepatch_server_url": ""})
    wait_blocked(juju)


def test_livepatch_server_set_fails(juju: jubilant.Juju):
    juju.config(
        APP, {"livepatch_server_url": "https://www.example.com", "livepatch_token": "new-token"}
    )
    unit = wait_blocked_on_error(juju)
    assert "new-token" not in unit.workload_status.message


def test_detach_subscription(juju: jubilant.Juju):
    juju.config(APP, {"token": ""})
    wait_blocked(juju)


@pytest.mark.parametrize("security_url", ["", "https://offline.ubuntu.com/security"])
def test_set_security_url(juju: jubilant.Juju, security_url: str):
    juju.config(
        APP,
        # Use default Livepatch configs to ensure this test is not dependent on a valid
        # Livepatch token or URL.
        {
            "livepatch_server_url": "",
            "livepatch_token": "",
            "security_url": security_url,
            "token": TEST_TOKEN,
        },
    )
    wait_active(juju)

    # Detach from pro subscription, so the next case starts from blocked and waiting for active
    # can't pass before its config change is applied.
    juju.config(APP, {"token": ""})
    wait_blocked(juju)


@pytest.mark.parametrize(
    "config_key, test_value",
    [
        ("apt_news_url", "https://news.example.com"),
        ("vulnerability_data_url_prefix", "https://vun.example.com"),
    ],
)
def test_ua_url_configs(juju: jubilant.Juju, config_key: str, test_value: str):
    """Verify that URL-based configs can be set and unset on the live unit."""
    # 1. Setup: Ensure clean state and active status
    juju.config(APP, {config_key: "", "token": TEST_TOKEN})
    wait_active(juju)

    # 2. Set Value: Update config and verify CLI output. The unit is already active, so also wait
    # for the value to reach the Pro client: both hold only once the config change is applied.
    juju.config(APP, {config_key: test_value})
    juju.wait(
        lambda s: jubilant.all_active(s, APP) and test_value in pro_config(juju),
        error=jubilant.any_error,
    )
    assert config_key in pro_config(juju)

    # 3. Unset Value: Clear config and verify it is removed from CLI
    juju.config(APP, {config_key: ""})
    juju.wait(
        lambda s: jubilant.all_active(s, APP) and test_value not in pro_config(juju),
        error=jubilant.any_error,
    )
