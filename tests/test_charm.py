# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import json
from subprocess import CalledProcessError
from unittest import TestCase
from unittest.mock import patch, call

from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus
from ops.testing import Harness

from charm import UbuntuAdvantageCharm


class TestCharm(TestCase):
    def setUp(self):
        self.harness = Harness(UbuntuAdvantageCharm)
        self.addCleanup(self.harness.cleanup)

    @patch("subprocess.check_call")
    def test_config_changed_no_ppa(self, _check_call):
        self.harness.begin()
        self.harness.update_config({"ppa": ""})
        self.assertIsInstance(self.harness.model.unit.status, BlockedStatus)
        self.assertEqual(self.harness.model.unit.status.message, "No ppa configured")

    @patch("subprocess.check_call")
    def test_config_changed_no_token(self, _check_call):
        self.harness.begin()
        self.harness.update_config({"ppa": "ua-client/stable"})
        self.assertIsInstance(self.harness.model.unit.status, BlockedStatus)
        self.assertEqual(self.harness.model.unit.status.message, "No token configured")

    @patch("subprocess.call")
    @patch("subprocess.check_output")
    @patch("subprocess.check_call")
    def test_config_changed_fresh_install(self, _check_call, _check_output, _call):
        success = {
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
        _check_output.side_effect = [
            '{"attached":false}',
            json.dumps(success)
        ]
        _call.return_value = 0
        self.harness.begin()
        self.harness.update_config({"token": "test-token"})
        self.assertEqual(_check_call.call_count, 3)
        _check_call.assert_has_calls([
            call(["add-apt-repository", "--yes", "ppa:ua-client/stable"]),
            call(["apt", "update"]),
            call(["apt", "install", "--yes", "--quiet", "ubuntu-advantage-tools"])
        ])
        self.assertEqual(_call.call_count, 1)
        _call.assert_has_calls([
            call(["ubuntu-advantage", "attach", "test-token"])
        ])
        self.assertEqual(self.harness.charm._state.ppa, "ppa:ua-client/stable")
        self.assertEqual(self.harness.charm._state.hashed_token,
                         "4c5dc9b7708905f77f5e5d16316b5dfb425e68cb326dcd55a860e90a7707031e")
        self.assertIsInstance(self.harness.model.unit.status, ActiveStatus)
        self.assertEqual(self.harness.model.unit.status.message,
                         "attached (esm-apps,esm-infra,livepatch)")

    @patch("subprocess.check_call")
    def test_config_changed_apt_failure(self, _check_call):
        _check_call.side_effect = CalledProcessError("apt failure", "add-apt-repository")
        self.harness.begin()
        with self.assertRaises(CalledProcessError):
            self.harness.update_config({"token": "test-token"})
        self.assertIsInstance(self.harness.model.unit.status, MaintenanceStatus)

    @patch("subprocess.check_call")
    def test_config_changed_unmodified_ppa(self, _check_call):
        self.harness.begin()
        self.harness.charm._state.ppa = "ppa:ua-client/stable"
        self.harness.update_config({"ppa": "ppa:ua-client/stable"})
        self.assertEqual(_check_call.call_count, 0)
        self.assertEqual(self.harness.charm._state.ppa, "ppa:ua-client/stable")

    @patch("subprocess.check_call")
    def test_config_changed_modified_ppa(self, _check_call):
        self.harness.begin()
        self.harness.charm._state.ppa = "ppa:ua-client/stable"
        self.harness.update_config({"ppa": "ppa:different-client/unstable"})
        self.assertEqual(_check_call.call_count, 3)
        _check_call.assert_has_calls([
            call(["add-apt-repository", "--yes", "ppa:different-client/unstable"]),
            call(["apt", "update"]),
            call(["apt", "install", "--yes", "--quiet", "ubuntu-advantage-tools"])
        ])
        self.assertEqual(self.harness.charm._state.ppa, "ppa:different-client/unstable")

    @patch("subprocess.check_call")
    def test_config_changed_modified_ppa_apt_failure(self, _check_call):
        _check_call.side_effect = CalledProcessError("apt failure", "add-apt-repository")
        self.harness.begin()
        self.harness.charm._state.ppa = "ppa:ua-client/stable"
        with self.assertRaises(CalledProcessError):
            self.harness.update_config({"ppa": "ppa:different-client/unstable"})
        self.assertEqual(self.harness.charm._state.ppa, "ppa:ua-client/stable")
        self.assertIsInstance(self.harness.model.unit.status, MaintenanceStatus)

    @patch("subprocess.call")
    @patch("subprocess.check_output")
    @patch("subprocess.check_call")
    def test_config_changed_reattach(self, _check_call, _check_output, _call):
        success = {
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
        _check_output.side_effect = [
            '{"attached":true}',
            '{"attached":false}',
            json.dumps(success)
        ]
        _call.return_value = 0
        self.harness.begin()
        self.harness.charm._state.ppa = "ppa:ua-client/stable"
        self.harness.charm._state.hashed_token = \
            "4c5dc9b7708905f77f5e5d16316b5dfb425e68cb326dcd55a860e90a7707031e"
        self.harness.update_config({"token": "test-token-2"})
        self.assertEqual(_check_call.call_count, 1)
        _check_call.assert_has_calls([
            call(["ubuntu-advantage", "detach", "--assume-yes"])
        ])
        self.assertEqual(_call.call_count, 1)
        _call.assert_has_calls([
            call(["ubuntu-advantage", "attach", "test-token-2"])
        ])
        self.assertEqual(self.harness.charm._state.ppa, "ppa:ua-client/stable")
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
            '{"attached":false}'
        ]
        _call.return_value = 1
        self.harness.begin()
        self.harness.charm._state.ppa = "ppa:ua-client/stable"
        self.harness.update_config({"token": "test-token"})
        self.assertIsInstance(self.harness.model.unit.status, BlockedStatus)
        self.assertEqual(self.harness.model.unit.status.message,
                         "Error attaching, possibly an invalid token?")

    @patch("subprocess.call")
    @patch("subprocess.check_output")
    @patch("subprocess.check_call")
    def test_config_changed_xenial_returned_bytes(self, _check_call, _check_output, _call):
        success = {
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
        _check_output.side_effect = [
            bytes(json.dumps(success), "utf-8")
        ]
        self.harness.begin()
        self.harness.charm._state.ppa = "ppa:ua-client/stable"
        self.harness.charm._state.hashed_token = \
            "4c5dc9b7708905f77f5e5d16316b5dfb425e68cb326dcd55a860e90a7707031e"
        self.harness.update_config({"token": "test-token"})
        self.assertIsInstance(self.harness.model.unit.status, ActiveStatus)
        self.assertEqual(self.harness.model.unit.status.message,
                         "attached (esm-apps,esm-infra,livepatch)")
