# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import os
import shutil
from contextlib import contextmanager

import pytest
from ops.model import ActiveStatus, BlockedStatus
from pytest_operator.plugin import OpsTest

BUILD_TARGET = os.environ.get("PRO_CHARM_BUILD_TARGET")
assert BUILD_TARGET is not None
CHARM_NAME = BUILD_TARGET.split("_")[0]

# The base both the principal and the subordinate are deployed on, e.g. "ubuntu@24.04".
# It must be one of the bases the build target supports.
TEST_BASE = os.environ.get("PRO_CHARM_TEST_BASE")
assert TEST_BASE is not None

TEST_TOKEN = os.environ.get("PRO_CHARM_TEST_TOKEN")
assert TEST_TOKEN is not None
# Optional: tests that need a real Livepatch staging token are skipped without one.
TEST_LIVEPATCH_TOKEN = os.environ.get("PRO_CHARM_TEST_LIVEPATCH_STAGING_TOKEN")


@contextmanager
def configure_build(target):
    shutil.copyfile(f"charms/{target}/charmcraft.yaml", "charmcraft.yaml")
    try:
        yield
    finally:
        if os.path.exists("charmcraft.yaml"):
            os.remove("charmcraft.yaml")


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest):
    with configure_build(BUILD_TARGET):
        charms = await ops_test.build_charm(".", return_all=True)
    # Packed charm names list the bases they run on (e.g. ubuntu-pro_ubuntu-24.04-amd64.charm);
    # a target that packs a single charm without them only has that one.
    version = TEST_BASE.split("@")[1]
    charm = next((c for c in charms if f"ubuntu-{version}-" in c.name), charms[0])
    # Deploy with the Juju CLI rather than python-libjuju: libjuju resolves the charm for the
    # model's default base before applying the requested one, and does not know 26.04 at all.
    await ops_test.juju("deploy", "ubuntu", "--base", TEST_BASE, check=True)
    await ops_test.juju("deploy", charm, "--base", TEST_BASE, check=True)
    await ops_test.model.add_relation(
        "ubuntu",
        CHARM_NAME,
    )
    await ops_test.model.wait_for_idle()


async def test_status(ops_test: OpsTest):
    assert ops_test.model.applications["ubuntu"].status == ActiveStatus.name
    assert ops_test.model.applications[CHARM_NAME].status == BlockedStatus.name


async def test_attach_invalid_token(ops_test: OpsTest):
    charm = ops_test.model.applications[CHARM_NAME]
    await charm.set_config({"token": ""})
    await ops_test.model.wait_for_idle()

    await charm.set_config({"token": "new-token-2"})
    await ops_test.model.wait_for_idle()

    expected_error = "stderr: Invalid token."
    unit = charm.units[0]
    assert unit.workload_status == BlockedStatus.name
    assert expected_error in unit.workload_status_message
    assert "new-token-2" not in unit.workload_status_message


async def test_attach_default_services(ops_test: OpsTest):
    charm = ops_test.model.applications[CHARM_NAME]

    # Attach to pro subscription without specifying services
    await charm.set_config({"token": TEST_TOKEN})
    await ops_test.model.wait_for_idle()

    unit = charm.units[0]
    assert unit.workload_status == ActiveStatus.name
    assert unit.workload_status_message == "Attached (esm-apps,esm-infra)"

    # Detach from pro subscription
    await charm.set_config({"token": ""})
    await ops_test.model.wait_for_idle()
    assert unit.workload_status == BlockedStatus.name


async def test_attach_services(ops_test: OpsTest):
    charm = ops_test.model.applications[CHARM_NAME]

    # Attach with an explicit services list, "esm-infra" alone still differs from the default
    # (esm-apps,esm-infra), so it proves the override is applied.
    await charm.set_config({"services": "esm-infra", "token": TEST_TOKEN})
    await ops_test.model.wait_for_idle()

    unit = charm.units[0]
    assert unit.workload_status == ActiveStatus.name
    assert unit.workload_status_message == "Attached (esm-infra)"

    # Detach from pro subscription
    await charm.set_config({"token": "", "services": ""})
    await ops_test.model.wait_for_idle()
    assert unit.workload_status == BlockedStatus.name


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

    assert unit.workload_status == ActiveStatus.name
    assert unit.workload_status_message == "Attached (esm-infra)"

    # Detach from pro subscription
    await charm.set_config({"token": "", "services": ""})
    await ops_test.model.wait_for_idle()
    assert unit.workload_status == BlockedStatus.name


async def test_empty_livepatch_config(ops_test: OpsTest):
    charm = ops_test.model.applications[CHARM_NAME]

    await charm.set_config({"token": TEST_TOKEN, "livepatch_token": ""})
    await ops_test.model.wait_for_idle()

    unit = charm.units[0]
    assert unit.workload_status == ActiveStatus.name

    # Detach from pro subscription
    await charm.set_config({"token": ""})
    await ops_test.model.wait_for_idle()
    assert unit.workload_status == BlockedStatus.name


@pytest.mark.skipif(
    not TEST_LIVEPATCH_TOKEN, reason="PRO_CHARM_TEST_LIVEPATCH_STAGING_TOKEN is not set"
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
    assert unit.workload_status == ActiveStatus.name

    # Detach from pro subscription and livepatch
    await charm.set_config({"token": "", "livepatch_token": "", "livepatch_server_url": ""})
    await ops_test.model.wait_for_idle()
    assert unit.workload_status == BlockedStatus.name


async def test_livepatch_server_set_fails(ops_test: OpsTest):
    charm = ops_test.model.applications[CHARM_NAME]
    await charm.set_config(
        {"livepatch_server_url": "https://www.example.com", "livepatch_token": "new-token"}
    )
    await ops_test.model.wait_for_idle()
    unit = charm.units[0]
    assert unit.workload_status == BlockedStatus.name
    assert "new-token" not in unit.workload_status_message


async def test_detach_subscription(ops_test: OpsTest):
    charm = ops_test.model.applications[CHARM_NAME]
    await charm.set_config({"token": ""})
    await ops_test.model.wait_for_idle()

    unit = charm.units[0]
    assert unit.workload_status == BlockedStatus.name


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
    assert unit.workload_status == ActiveStatus.name


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
