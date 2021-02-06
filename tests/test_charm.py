# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import json
from subprocess import CalledProcessError
from unittest import TestCase
from unittest.mock import patch, call

from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus
from ops.testing import Harness

from charm import UbuntuAdvantageCharm


STATUS_ATTACHED = json.dumps(
    {
        "attached": True,
        "services": [
            {
                "name": "esm-apps",
                "status": "enabled"
            },
            {
                "name": "esm-infra",
                "status": "enabled"
            },
            {
                "name": "livepatch",
                "status": "enabled"
            }
        ]
    }
)


STATUS_DETACHED = json.dumps(
    {
        "attached": False,
        "services": [
            {
                "name": "esm-apps",
                "available": "yes"
            },
            {
                "name": "esm-infra",
                "available": "yes"
            },
            {
                "name": "livepatch",
                "available": "yes"
            }
        ]
    }
)


class TestCharm(TestCase):
    def setUp(self):
        self.harness = Harness(UbuntuAdvantageCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    @patch("subprocess.check_call")
    def test_config_changed_defaults(self, _check_call):
        self.harness.update_config()
        self.assertEqual(_check_call.call_count, 3)
        _check_call.assert_has_calls([
            call(["apt", "remove", "--yes", "--quiet", "ubuntu-advantage-tools"]),
            call(["apt", "update"]),
            call(["apt", "install", "--yes", "--quiet", "ubuntu-advantage-tools"])
        ])
        self.assertIsNone(self.harness.charm._state.ppa)
        self.assertFalse(self.harness.charm._state.package_needs_installing)
        self.assertIsNone(self.harness.charm._state.hashed_token)
        self.assertIsInstance(self.harness.model.unit.status, BlockedStatus)
        self.assertEqual(self.harness.model.unit.status.message, "No token configured")

    @patch("subprocess.check_call")
    def test_config_changed_does_not_install_twice(self, _check_call):
        self.harness.update_config()
        self.assertEqual(_check_call.call_count, 3)
        _check_call.assert_has_calls([
            call(["apt", "remove", "--yes", "--quiet", "ubuntu-advantage-tools"]),
            call(["apt", "update"]),
            call(["apt", "install", "--yes", "--quiet", "ubuntu-advantage-tools"])
        ])
        self.assertFalse(self.harness.charm._state.package_needs_installing)
        _check_call.reset_mock()
        self.harness.update_config()
        self.assertEqual(_check_call.call_count, 0)
        self.assertFalse(self.harness.charm._state.package_needs_installing)

    @patch("subprocess.check_call")
    def test_config_changed_ppa_new(self, _check_call):
        self.harness.update_config({"ppa": "ppa:ua-client/stable"})
        self.assertEqual(_check_call.call_count, 4)
        _check_call.assert_has_calls([
            call(["add-apt-repository", "--yes", "ppa:ua-client/stable"]),
            call(["apt", "remove", "--yes", "--quiet", "ubuntu-advantage-tools"]),
            call(["apt", "update"]),
            call(["apt", "install", "--yes", "--quiet", "ubuntu-advantage-tools"])
        ])
        self.assertEqual(self.harness.charm._state.ppa, "ppa:ua-client/stable")
        self.assertFalse(self.harness.charm._state.package_needs_installing)

    @patch("subprocess.check_call")
    def test_config_changed_ppa_updated(self, _check_call):
        self.harness.update_config({"ppa": "ppa:ua-client/stable"})
        self.assertEqual(_check_call.call_count, 4)
        _check_call.assert_has_calls([
            call(["add-apt-repository", "--yes", "ppa:ua-client/stable"]),
            call(["apt", "remove", "--yes", "--quiet", "ubuntu-advantage-tools"]),
            call(["apt", "update"]),
            call(["apt", "install", "--yes", "--quiet", "ubuntu-advantage-tools"])
        ])
        self.assertEqual(self.harness.charm._state.ppa, "ppa:ua-client/stable")
        self.assertFalse(self.harness.charm._state.package_needs_installing)
        _check_call.reset_mock()
        self.harness.update_config({"ppa": "ppa:different-client/unstable"})
        self.assertEqual(_check_call.call_count, 5)
        _check_call.assert_has_calls([
            call(["add-apt-repository", "--remove", "--yes", "ppa:ua-client/stable"]),
            call(["add-apt-repository", "--yes", "ppa:different-client/unstable"]),
            call(["apt", "remove", "--yes", "--quiet", "ubuntu-advantage-tools"]),
            call(["apt", "update"]),
            call(["apt", "install", "--yes", "--quiet", "ubuntu-advantage-tools"])
        ])
        self.assertEqual(self.harness.charm._state.ppa, "ppa:different-client/unstable")
        self.assertFalse(self.harness.charm._state.package_needs_installing)

    @patch("subprocess.check_call")
    def test_config_changed_ppa_unmodified(self, _check_call):
        self.harness.update_config({"ppa": "ppa:ua-client/stable"})
        self.assertEqual(_check_call.call_count, 4)
        _check_call.assert_has_calls([
            call(["add-apt-repository", "--yes", "ppa:ua-client/stable"]),
            call(["apt", "remove", "--yes", "--quiet", "ubuntu-advantage-tools"]),
            call(["apt", "update"]),
            call(["apt", "install", "--yes", "--quiet", "ubuntu-advantage-tools"])
        ])
        self.assertEqual(self.harness.charm._state.ppa, "ppa:ua-client/stable")
        self.assertFalse(self.harness.charm._state.package_needs_installing)
        _check_call.reset_mock()
        self.harness.update_config({"ppa": "ppa:ua-client/stable"})
        self.assertEqual(_check_call.call_count, 0)
        self.assertEqual(self.harness.charm._state.ppa, "ppa:ua-client/stable")
        self.assertFalse(self.harness.charm._state.package_needs_installing)

    @patch("subprocess.check_call")
    def test_config_changed_ppa_apt_failure(self, _check_call):
        _check_call.side_effect = CalledProcessError("apt failure", "add-apt-repository")
        with self.assertRaises(CalledProcessError):
            self.harness.update_config({"ppa": "ppa:ua-client/stable"})
        self.assertIsNone(self.harness.charm._state.ppa)
        self.assertTrue(self.harness.charm._state.package_needs_installing)
        self.assertIsInstance(self.harness.model.unit.status, MaintenanceStatus)

    @patch("subprocess.call")
    @patch("subprocess.check_output")
    @patch("subprocess.check_call")
    def test_config_changed_token_unattached(self, _check_call, _check_output, _call):
        _check_output.side_effect = [
            STATUS_DETACHED,
            STATUS_ATTACHED
        ]
        _call.return_value = 0
        self.harness.update_config({"token": "test-token"})
        self.assertEqual(_call.call_count, 1)
        _call.assert_has_calls([
            call(["ubuntu-advantage", "attach", "test-token"])
        ])
        self.assertEqual(self.harness.charm._state.hashed_token,
                         "4c5dc9b7708905f77f5e5d16316b5dfb425e68cb326dcd55a860e90a7707031e")
        self.assertIsInstance(self.harness.model.unit.status, ActiveStatus)
        self.assertEqual(self.harness.model.unit.status.message,
                         "attached (esm-apps,esm-infra,livepatch)")

    @patch("subprocess.call")
    @patch("subprocess.check_output")
    @patch("subprocess.check_call")
    def test_config_changed_token_reattach(self, _check_call, _check_output, _call):
        _check_output.side_effect = [
            STATUS_DETACHED,
            STATUS_ATTACHED
        ]
        _call.return_value = 0
        self.harness.update_config({"token": "test-token"})
        self.assertEqual(_check_call.call_count, 3)
        _check_call.assert_has_calls([
            call(["apt", "remove", "--yes", "--quiet", "ubuntu-advantage-tools"]),
            call(["apt", "update"]),
            call(["apt", "install", "--yes", "--quiet", "ubuntu-advantage-tools"])
        ])
        self.assertEqual(_call.call_count, 1)
        _call.assert_has_calls([
            call(["ubuntu-advantage", "attach", "test-token"])
        ])
        self.assertEqual(self.harness.charm._state.hashed_token,
                         "4c5dc9b7708905f77f5e5d16316b5dfb425e68cb326dcd55a860e90a7707031e")
        _check_output.side_effect = [
            STATUS_ATTACHED,
            STATUS_DETACHED,
            STATUS_ATTACHED
        ]
        _call.reset_mock()
        _check_call.reset_mock()
        self.harness.update_config({"token": "test-token-2"})
        self.assertEqual(_check_call.call_count, 1)
        _check_call.assert_has_calls([
            call(["ubuntu-advantage", "detach", "--assume-yes"])
        ])
        self.assertEqual(_call.call_count, 1)
        _call.assert_has_calls([
            call(["ubuntu-advantage", "attach", "test-token-2"])
        ])
        self.assertEqual(self.harness.charm._state.hashed_token,
                         "ab8a83efb364bf3f6739348519b53c8e8e0f7b4c06b6eeb881ad73dcf0059107")
        self.assertIsInstance(self.harness.model.unit.status, ActiveStatus)
        self.assertEqual(self.harness.model.unit.status.message,
                         "attached (esm-apps,esm-infra,livepatch)")

    @patch("subprocess.call")
    @patch("subprocess.check_output")
    @patch("subprocess.check_call")
    def test_config_changed_attach_failure(self, _check_call, _check_output, _call):
        _check_output.side_effect = [
            STATUS_DETACHED
        ]
        _call.return_value = 1
        self.harness.update_config({"token": "test-token"})
        self.assertIsInstance(self.harness.model.unit.status, BlockedStatus)
        self.assertEqual(self.harness.model.unit.status.message,
                         "Error attaching, possibly an invalid token?")

    @patch("subprocess.call")
    @patch("subprocess.check_output")
    @patch("subprocess.check_call")
    def test_config_changed_token_detach(self, _check_call, _check_output, _call):
        _check_output.side_effect = [
            STATUS_DETACHED,
            STATUS_ATTACHED
        ]
        _call.return_value = 0
        self.harness.update_config({"token": "test-token"})
        self.assertEqual(_check_call.call_count, 3)
        _check_call.assert_has_calls([
            call(["apt", "remove", "--yes", "--quiet", "ubuntu-advantage-tools"]),
            call(["apt", "update"]),
            call(["apt", "install", "--yes", "--quiet", "ubuntu-advantage-tools"])
        ])
        self.assertEqual(_call.call_count, 1)
        _call.assert_has_calls([
            call(["ubuntu-advantage", "attach", "test-token"])
        ])
        self.assertEqual(self.harness.charm._state.hashed_token,
                         "4c5dc9b7708905f77f5e5d16316b5dfb425e68cb326dcd55a860e90a7707031e")
        _check_output.side_effect = [
            STATUS_ATTACHED,
            STATUS_DETACHED,
            STATUS_DETACHED
        ]
        _call.reset_mock()
        _check_call.reset_mock()
        self.harness.update_config({"token": ""})
        self.assertEqual(_check_call.call_count, 1)
        _check_call.assert_has_calls([
            call(["ubuntu-advantage", "detach", "--assume-yes"])
        ])
        self.assertEqual(_call.call_count, 0)
        self.assertIsNone(self.harness.charm._state.hashed_token)
        self.assertIsInstance(self.harness.model.unit.status, BlockedStatus)
        self.assertEqual(self.harness.model.unit.status.message, "No token configured")

    @patch("subprocess.call")
    @patch("subprocess.check_output")
    @patch("subprocess.check_call")
    def test_config_changed_check_output_returns_bytes(self, _check_call, _check_output, _call):
        _check_output.side_effect = [
            bytes(STATUS_DETACHED, "utf-8"),
            bytes(STATUS_ATTACHED, "utf-8")
        ]
        _call.return_value = 0
        self.harness.update_config({"token": "test-token"})
        self.assertIsInstance(self.harness.model.unit.status, ActiveStatus)
        self.assertEqual(self.harness.model.unit.status.message,
                         "attached (esm-apps,esm-infra,livepatch)")
