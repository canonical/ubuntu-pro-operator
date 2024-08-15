# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import os

import pytest
from ops.model import ActiveStatus, BlockedStatus
from pytest_operator.plugin import OpsTest


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest):
    charm = await ops_test.build_charm(".")
    await ops_test.model.deploy("ubuntu")
    await ops_test.model.deploy(charm, num_units=0)
    await ops_test.model.add_relation(
        "ubuntu",
        "ubuntu-advantage",
    )
    await ops_test.model.wait_for_idle()


async def test_status(ops_test: OpsTest):
    assert ops_test.model.applications["ubuntu"].status == ActiveStatus.name
    assert ops_test.model.applications["ubuntu-advantage"].status == BlockedStatus.name


async def test_attach_invalid_token(ops_test: OpsTest):
    charm = ops_test.model.applications["ubuntu-advantage"]
    await charm.set_config({"token": ""})
    await ops_test.model.wait_for_idle()

    await charm.set_config({"token": "new-token-2"})
    await ops_test.model.wait_for_idle()

    expected_error = "Failed running command '['ubuntu-advantage', 'attach', 'new-token-2']' \
[exit status: 1].\nstderr: Invalid token. See https://ubuntu.com/pro/dashboard\n\nstdout: "
    unit = charm.units[0]
    assert unit.workload_status == BlockedStatus.name
    assert unit.workload_status_message == expected_error


async def test_attach_services(ops_test: OpsTest):
    # Set test token to environment variable PRO_CHARM_TEST_TOKEN
    # bash: export PRO_CHARM_TEST_TOKEN="your-token"
    test_token = os.environ.get("PRO_CHARM_TEST_TOKEN")
    charm = ops_test.model.applications["ubuntu-advantage"]

    # Attach to pro subscription with services
    await charm.set_config({"services": "esm-infra,cis", "token": f"{test_token}"})
    await ops_test.model.wait_for_idle()

    unit = charm.units[0]
    assert unit.workload_status == ActiveStatus.name
    assert unit.workload_status_message == "Attached (esm-infra,usg)"

    # Detach from pro subscription
    await charm.set_config({"token": "", "services": ""})
    await ops_test.model.wait_for_idle()
    assert unit.workload_status == BlockedStatus.name


async def test_empty_livepatch_config(ops_test: OpsTest):
    charm = ops_test.model.applications["ubuntu-advantage"]
    test_token = os.environ.get("PRO_CHARM_TEST_TOKEN")

    await charm.set_config({"token": test_token, "livepatch_token": ""})
    await ops_test.model.wait_for_idle()

    unit = charm.units[0]
    assert unit.workload_status == ActiveStatus.name

    # Detach from pro subscription
    await charm.set_config({"token": ""})
    await ops_test.model.wait_for_idle()
    assert unit.workload_status == BlockedStatus.name


async def test_livepatch_server_success(ops_test: OpsTest):
    charm = ops_test.model.applications["ubuntu-advantage"]
    test_pro_token = os.environ.get("PRO_CHARM_TEST_TOKEN")
    test_livepatch_token = os.environ.get("PRO_CHARM_TEST_LIVEPATCH_STAGING_TOKEN")

    await charm.set_config(
        {
            "livepatch_server_url": "https://livepatch.staging.canonical.com",
            "livepatch_token": test_livepatch_token,
            "token": test_pro_token,
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
    charm = ops_test.model.applications["ubuntu-advantage"]
    await charm.set_config(
        {"livepatch_server_url": "https://www.example.com", "livepatch_token": "new-token"}
    )
    await ops_test.model.wait_for_idle()
    unit = charm.units[0]
    assert unit.workload_status == BlockedStatus.name


async def test_detach_subscription(ops_test: OpsTest):
    charm = ops_test.model.applications["ubuntu-advantage"]
    await charm.set_config({"token": ""})
    await ops_test.model.wait_for_idle()

    unit = charm.units[0]
    assert unit.workload_status == BlockedStatus.name
