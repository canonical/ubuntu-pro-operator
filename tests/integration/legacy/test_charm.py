# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Integration tests for 18.04 on Juju 2.9. Keep in step with tests/integration/test_charm.py."""

import json
import os
import pathlib

import pytest
from pytest_operator.plugin import OpsTest

# The packed charm under test, e.g. ubuntu-pro_ubuntu-16.04-...-ubuntu-22.04-amd64.charm.
CHARM_PATH = os.environ.get("CHARM_PATH")
assert CHARM_PATH is not None
CHARM_PATH = pathlib.Path(CHARM_PATH).resolve()
# Packed charm file names start with the charm name.
CHARM_NAME = CHARM_PATH.name.split("_")[0]

# The series both the principal and the subordinate are deployed on, e.g. "bionic".
TEST_SERIES = os.environ.get("PRO_CHARM_TEST_SERIES")
assert TEST_SERIES is not None

TEST_TOKEN = os.environ.get("PRO_CHARM_TEST_TOKEN")
assert TEST_TOKEN is not None
# Optional: tests that need a real Livepatch staging token are skipped without one.
TEST_LIVEPATCH_TOKEN = os.environ.get("PRO_CHARM_TEST_LIVEPATCH_STAGING_TOKEN")

ACTIVE = "active"
BLOCKED = "blocked"


@pytest.mark.abort_on_fail
async def test_deploy(ops_test: OpsTest):
    await ops_test.model.deploy("ubuntu", series=TEST_SERIES)
    await ops_test.model.deploy(CHARM_PATH, CHARM_NAME, series=TEST_SERIES, num_units=0)
    await ops_test.model.add_relation("ubuntu", CHARM_NAME)
    await ops_test.model.wait_for_idle(timeout=15 * 60)


async def test_status(ops_test: OpsTest):
    assert ops_test.model.applications["ubuntu"].status == ACTIVE
    assert ops_test.model.applications[CHARM_NAME].status == BLOCKED


async def test_attach_invalid_token(ops_test: OpsTest):
    charm = ops_test.model.applications[CHARM_NAME]
    await charm.set_config({"token": ""})
    await ops_test.model.wait_for_idle()

    await charm.set_config({"token": "new-token-2"})
    await ops_test.model.wait_for_idle()

    expected_error = "stderr: Invalid token."
    unit = charm.units[0]
    assert unit.workload_status == BLOCKED
    assert expected_error in unit.workload_status_message
    assert "new-token-2" not in unit.workload_status_message


async def test_attach_default_services(ops_test: OpsTest):
    charm = ops_test.model.applications[CHARM_NAME]

    # Attach to pro subscription without specifying services
    await charm.set_config({"token": TEST_TOKEN})
    await ops_test.model.wait_for_idle()

    unit = charm.units[0]
    assert unit.workload_status == ACTIVE
    assert unit.workload_status_message == "Attached (esm-apps,esm-infra)"

    # Detach from pro subscription
    await charm.set_config({"token": ""})
    await ops_test.model.wait_for_idle()
    assert unit.workload_status == BLOCKED


async def test_attach_services(ops_test: OpsTest):
    charm = ops_test.model.applications[CHARM_NAME]

    # Attach with an explicit services list, "esm-infra" alone still differs from the default
    # (esm-apps,esm-infra), so it proves the override is applied.
    await charm.set_config({"services": "esm-infra", "token": TEST_TOKEN})
    await ops_test.model.wait_for_idle()

    unit = charm.units[0]
    assert unit.workload_status == ACTIVE
    assert unit.workload_status_message == "Attached (esm-infra)"

    # Detach from pro subscription
    await charm.set_config({"token": "", "services": ""})
    await ops_test.model.wait_for_idle()
    assert unit.workload_status == BLOCKED


async def test_detach_before_attach(ops_test: OpsTest):
    charm = ops_test.model.applications[CHARM_NAME]
    unit = charm.units[0]

    # Attach to pro subscription with services "manually" to get the unit
    # in a weird state to test the detach before attach logic.
    action = await unit.run(f"sudo pro attach {TEST_TOKEN} --no-auto-enable")
    await action.wait()
    action = await unit.run("sudo pro api u.pro.status.is_attached.v1")
    await action.wait()
    assert json.loads(action.results["stdout"])["data"]["attributes"]["is_attached"] is True

    # Attach to pro subscription with services
    # This will detach the existing attachment and then attach.
    # We will know the second attachment succeeded because it will enable esm-infra.
    await charm.set_config({"services": "esm-infra", "token": TEST_TOKEN})
    await ops_test.model.wait_for_idle()

    assert unit.workload_status == ACTIVE
    assert unit.workload_status_message == "Attached (esm-infra)"

    # Detach from pro subscription
    await charm.set_config({"token": "", "services": ""})
    await ops_test.model.wait_for_idle()
    assert unit.workload_status == BLOCKED


async def test_empty_livepatch_config(ops_test: OpsTest):
    charm = ops_test.model.applications[CHARM_NAME]

    await charm.set_config({"token": TEST_TOKEN, "livepatch_token": ""})
    await ops_test.model.wait_for_idle()

    unit = charm.units[0]
    assert unit.workload_status == ACTIVE

    # Detach from pro subscription
    await charm.set_config({"token": ""})
    await ops_test.model.wait_for_idle()
    assert unit.workload_status == BLOCKED


@pytest.mark.skipif(
    not TEST_LIVEPATCH_TOKEN, reason="PRO_CHARM_TEST_LIVEPATCH_STAGING_TOKEN not set"
)
async def test_livepatch_server_success(ops_test: OpsTest):
    charm = ops_test.model.applications[CHARM_NAME]

    await charm.set_config(
        {
            "livepatch_server_url": "https://livepatch.staging.canonical.com",
            "livepatch_token": TEST_LIVEPATCH_TOKEN,
            "token": TEST_TOKEN,
        }
    )
    await ops_test.model.wait_for_idle()

    unit = charm.units[0]
    assert unit.workload_status == ACTIVE

    # Detach from pro subscription and livepatch
    await charm.set_config({"token": "", "livepatch_token": "", "livepatch_server_url": ""})
    await ops_test.model.wait_for_idle()
    assert unit.workload_status == BLOCKED


async def test_livepatch_server_set_fails(ops_test: OpsTest):
    charm = ops_test.model.applications[CHARM_NAME]
    await charm.set_config(
        {"livepatch_server_url": "https://www.example.com", "livepatch_token": "new-token"}
    )
    await ops_test.model.wait_for_idle()
    unit = charm.units[0]
    assert unit.workload_status == BLOCKED
    assert "new-token" not in unit.workload_status_message


async def test_detach_subscription(ops_test: OpsTest):
    charm = ops_test.model.applications[CHARM_NAME]
    await charm.set_config({"token": ""})
    await ops_test.model.wait_for_idle()

    unit = charm.units[0]
    assert unit.workload_status == BLOCKED


@pytest.mark.parametrize("security_url", ["", "https://offline.ubuntu.com/security"])
async def test_set_security_url(ops_test: OpsTest, security_url: str):
    charm = ops_test.model.applications[CHARM_NAME]

    await charm.set_config(
        # Use default Livepatch configs to ensure this test is not dependent on a valid
        # Livepatch token or URL.
        {
            "livepatch_server_url": "",
            "livepatch_token": "",
            "security_url": security_url,
            "token": TEST_TOKEN,
        }
    )
    await ops_test.model.wait_for_idle()

    unit = charm.units[0]
    assert unit.workload_status == ACTIVE


@pytest.mark.parametrize(
    "config_key, test_value",
    [
        ("apt_news_url", "https://news.example.com"),
        ("vulnerability_data_url_prefix", "https://vun.example.com"),
    ],
)
async def test_ua_url_configs(ops_test: OpsTest, config_key: str, test_value: str):
    """Verify that URL-based configs can be set and unset on the live unit."""
    charm = ops_test.model.applications[CHARM_NAME]
    unit = charm.units[0]

    # 1. Setup: Ensure clean state and active status
    await charm.set_config({config_key: "", "token": TEST_TOKEN})
    await ops_test.model.wait_for_idle(status="active")

    # 2. Set Value: Update config and verify CLI output
    await charm.set_config({config_key: test_value})
    await ops_test.model.wait_for_idle(status="active", timeout=600)

    action = await unit.run("pro config show")
    await action.wait()
    stdout = action.results.get("stdout", "")
    assert config_key in stdout
    assert test_value in stdout

    # 3. Unset Value: Clear config and verify it is removed from CLI
    await charm.set_config({config_key: ""})
    await ops_test.model.wait_for_idle(status="active")

    action = await unit.run("pro config show")
    await action.wait()
    assert test_value not in action.results.get("stdout", "")
