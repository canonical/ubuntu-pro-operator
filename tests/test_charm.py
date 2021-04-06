# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import json
from subprocess import CalledProcessError
from textwrap import dedent
from unittest import TestCase
from unittest.mock import call, mock_open, patch

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

# Default contents of /etc/ubuntu-advantage/uaclient.conf
DEFAULT_CLIENT_CONFIG = """
# Ubuntu-Advantage client config file.
contract_url: 'https://contracts.canonical.com'
data_dir: /var/lib/ubuntu-advantage
log_level: debug
log_file: /var/log/ubuntu-advantage.log
"""


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
    def test_config_changed_ppa_unset(self, _check_call):
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
        self.harness.update_config({"ppa": ""})
        self.assertEqual(_check_call.call_count, 4)
        _check_call.assert_has_calls([
            call(["add-apt-repository", "--remove", "--yes", "ppa:ua-client/stable"]),
            call(["apt", "remove", "--yes", "--quiet", "ubuntu-advantage-tools"]),
            call(["apt", "update"]),
            call(["apt", "install", "--yes", "--quiet", "ubuntu-advantage-tools"])
        ])
        self.assertIsNone(self.harness.charm._state.ppa)
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
                         "Attached (esm-apps,esm-infra,livepatch)")

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
                         "Attached (esm-apps,esm-infra,livepatch)")

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
    def test_config_changed_token_update_after_block(self, _check_call, _check_output, _call):
        self.harness.update_config()
        self.assertIsInstance(self.harness.model.unit.status, BlockedStatus)
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
        self.assertIsInstance(self.harness.model.unit.status, ActiveStatus)

    @patch("subprocess.call")
    @patch("subprocess.check_output")
    @patch("subprocess.check_call")
    def test_config_changed_token_contains_newline(self, _check_call, _check_output, _call):
        _check_output.side_effect = [
            STATUS_DETACHED,
            STATUS_ATTACHED
        ]
        _call.return_value = 0
        self.harness.update_config({"token": "test-token\n"})
        self.assertEqual(_call.call_count, 1)
        _call.assert_has_calls([
            call(["ubuntu-advantage", "attach", "test-token"])
        ])
        self.assertEqual(self.harness.charm._state.hashed_token,
                         "4c5dc9b7708905f77f5e5d16316b5dfb425e68cb326dcd55a860e90a7707031e")

    @patch("subprocess.check_call")
    def test_config_changed_ppa_contains_newline(self, _check_call):
        self.harness.update_config({"ppa": "ppa:ua-client/stable\n"})
        self.assertEqual(_check_call.call_count, 4)
        _check_call.assert_has_calls([
            call(["add-apt-repository", "--yes", "ppa:ua-client/stable"]),
            call(["apt", "remove", "--yes", "--quiet", "ubuntu-advantage-tools"]),
            call(["apt", "update"]),
            call(["apt", "install", "--yes", "--quiet", "ubuntu-advantage-tools"])
        ])
        self.assertEqual(self.harness.charm._state.ppa, "ppa:ua-client/stable")

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
                         "Attached (esm-apps,esm-infra,livepatch)")

    @patch("builtins.open")
    @patch("subprocess.check_output")
    @patch("subprocess.check_call")
    @patch("subprocess.call")
    def test_config_changed_contract_url(self, _call, _check_call, _check_output, _open):
        """
        Setting the contract_url config will cause the ua client config file to
        be written.
        """
        _check_output.side_effect = [
            STATUS_DETACHED,
        ]
        mock_open(_open, read_data=DEFAULT_CLIENT_CONFIG)

        self.harness.update_config({"contract_url": "https://contracts.staging.canonical.com"})
        _open.assert_called_with('/etc/ubuntu-advantage/uaclient.conf', 'w')
        handle = _open()
        expected = dedent("""\
            contract_url: https://contracts.staging.canonical.com
            data_dir: /var/lib/ubuntu-advantage
            log_file: /var/log/ubuntu-advantage.log
            log_level: debug
        """)
        _call.assert_not_called()
        self.assertEqual(_written(handle), expected)
        self.assertIsInstance(self.harness.model.unit.status, BlockedStatus)
        self.assertEqual(self.harness.model.unit.status.message, "No token configured")

    @patch("builtins.open")
    @patch("subprocess.check_output")
    @patch("subprocess.check_call")
    @patch("subprocess.call")
    def test_config_changed_contract_url_reattach(self, _call, _check_call, _check_output, _open):
        """
        If the contract url is altered of an attached instance (token is set),
        the instance will detach and reattach.
        """
        _check_output.side_effect = [
            STATUS_DETACHED,
            STATUS_ATTACHED,
        ]
        _call.return_value = 0
        mock_open(_open, read_data=DEFAULT_CLIENT_CONFIG)

        self.harness.update_config({"token": "test-token"})
        _call.assert_has_calls([
            call(["ubuntu-advantage", "attach", "test-token"])
        ])
        self.assertEqual(self.harness.charm._state.hashed_token,
                         "4c5dc9b7708905f77f5e5d16316b5dfb425e68cb326dcd55a860e90a7707031e")
        # Alter contract_url.
        _call.reset_mock()
        _check_call.reset_mock()
        _check_output.side_effect = [
            STATUS_ATTACHED,
            STATUS_ATTACHED,
        ]
        self.harness.update_config({"contract_url": "https://contracts.staging.canonical.com"})
        _open.assert_called_with('/etc/ubuntu-advantage/uaclient.conf', 'w')
        handle = _open()
        expected = dedent("""\
            contract_url: https://contracts.staging.canonical.com
            data_dir: /var/lib/ubuntu-advantage
            log_file: /var/log/ubuntu-advantage.log
            log_level: debug
        """)
        self.assertEqual(_written(handle), expected)
        _check_call.assert_has_calls([
            call(['ubuntu-advantage', 'detach', '--assume-yes'])
        ])
        _call.assert_has_calls([
            call(['ubuntu-advantage', 'attach', 'test-token'])
        ])
        self.assertIsInstance(self.harness.model.unit.status, ActiveStatus)
        self.assertEqual(self.harness.model.unit.status.message,
                         "Attached (esm-apps,esm-infra,livepatch)")

        # Check that a config change not involving the token or contract_url
        # is handled properly.
        _call.reset_mock()
        _open.reset_mock()
        _check_call.reset_mock()
        _check_output.side_effect = [
            STATUS_ATTACHED,
        ]
        self.harness.update_config()
        _open.assert_not_called()
        _call.assert_not_called()

    @patch("builtins.open")
    @patch("subprocess.check_output")
    @patch("subprocess.check_call")
    @patch("subprocess.call")
    def test_config_changed_unset_contract_url(self, _call, _check_call, _check_output, _open):
        """
        If the contract url value is unset from charm config, the default value
        will be used.
        """
        """
        Setting the contract_url config will cause the ua client config file to
        be written.
        """
        _check_output.side_effect = [
            STATUS_DETACHED,
            STATUS_DETACHED,
        ]
        mock_open(_open, read_data=DEFAULT_CLIENT_CONFIG)

        self.harness.update_config({"contract_url": "https://contracts.staging.canonical.com"})
        _open.assert_called_with('/etc/ubuntu-advantage/uaclient.conf', 'w')
        handle = _open()
        expected = dedent("""\
            contract_url: https://contracts.staging.canonical.com
            data_dir: /var/lib/ubuntu-advantage
            log_file: /var/log/ubuntu-advantage.log
            log_level: debug
        """)
        _call.assert_not_called()
        self.assertEqual(_written(handle), expected)
        self.assertIsInstance(self.harness.model.unit.status, BlockedStatus)
        self.assertEqual(self.harness.model.unit.status.message, "No token configured")

        _open.reset_mock()
        _call.reset_mock()
        _check_call.reset_mock()
        _check_output.side_effect = [
            STATUS_DETACHED,
            STATUS_DETACHED,
        ]
        self.harness.update_config({"contract_url": ''})
        _open.assert_called_with('/etc/ubuntu-advantage/uaclient.conf', 'w')
        handle = _open()
        expected = dedent("""\
            contract_url: https://contracts.canonical.com
            data_dir: /var/lib/ubuntu-advantage
            log_file: /var/log/ubuntu-advantage.log
            log_level: debug
        """)
        _call.assert_not_called()
        self.assertEqual(_written(handle), expected)
        self.assertIsInstance(self.harness.model.unit.status, BlockedStatus)
        self.assertEqual(self.harness.model.unit.status.message, "No token configured")


def _written(handle):
    contents = ''.join([''.join(a.args) for a in handle.write.call_args_list])
    return contents
