# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import os
import shutil
from contextlib import contextmanager

import pytest
from ops.model import ActiveStatus, BlockedStatus
from pytest_operator.plugin import OpsTest

BUILD_TARGET = os.environ.get("PRO_CHARM_BUILD_TARGET")
assert BUILD_TARGET is not None
CHARM_NAME = BUILD_TARGET.split("_")[0]

TEST_TOKEN = os.environ.get("PRO_CHARM_TEST_TOKEN")
assert TEST_TOKEN is not None
TEST_LIVEPATCH_TOKEN = os.environ.get("PRO_CHARM_TEST_LIVEPATCH_STAGING_TOKEN")
assert TEST_LIVEPATCH_TOKEN is not None


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
        charm = await ops_test.build_charm(".")
    await ops_test.model.deploy("ubuntu")
    await ops_test.model.deploy(charm, num_units=0)
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

    # Attach to pro subscription with services
    await charm.set_config({"services": "esm-infra,cis", "token": TEST_TOKEN})
    await ops_test.model.wait_for_idle()

    unit = charm.units[0]
    assert unit.workload_status == ActiveStatus.name
    assert unit.workload_status_message == "Attached (esm-infra,usg)"

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
