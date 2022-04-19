# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

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
    