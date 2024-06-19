# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import json
from subprocess import CalledProcessError
from textwrap import dedent
from unittest import TestCase
from unittest.mock import MagicMock, call, mock_open, patch

from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus
from ops.testing import Harness

from charm import UbuntuAdvantageCharm

STATUS_ATTACHED = json.dumps(
    {
        "attached": True,
        "services": [
            {"name": "esm-apps", "status": "enabled"},
            {"name": "esm-infra", "status": "enabled"},
            {"name": "livepatch", "status": "enabled"},
        ],
    }
)


STATUS_DETACHED = json.dumps(
    {
        "attached": False,
        "services": [
            {"name": "esm-apps", "available": "yes"},
            {"name": "esm-infra", "available": "yes"},
            {"name": "livepatch", "available": "yes"},
        ],
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

TEST_PROXY_URL = "http://squid.internal:3128"
TEST_NO_PROXY = "127.0.0.1,localhost,::1"


def _written(handle):
    contents = "".join(["".join(a.args) for a in handle.write.call_args_list])
    return contents


class TestCharm(TestCase):
    def setUp(self):
        self.addCleanup(patch.stopall)
        self.mocks = {
            "call": patch("subprocess.call").start(),
            "check_call": patch("subprocess.check_call").start(),
            "run": patch("subprocess.run").start(),
            "open": patch("builtins.open").start(),
            "environ": patch.dict("os.environ", clear=True).start(),
            "apt": patch("charm.apt").start(),
        }
        self.mocks["call"].return_value = 0
        self.mocks["run"].return_value = MagicMock(returncode=0, stderr="")
        mock_open(self.mocks["open"], read_data=DEFAULT_CLIENT_CONFIG)
        self.harness = Harness(UbuntuAdvantageCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()
        self.env = self.harness.charm.env

    def test_config_defaults(self):
        self.assertEqual(
            self.harness.charm.config.get("contract_url"), "https://contracts.canonical.com"
        )
        self.assertEqual(self.harness.charm.config.get("ppa"), "")
        self.assertEqual(self.harness.charm.config.get("token"), "")

    def test_config_changed_ppa_new(self):
        self.mocks["run"].return_value = MagicMock(returncode=0, stdout=STATUS_DETACHED)
        self.harness.update_config({"ppa": "ppa:ua-client/stable"})
        self.assertEqual(self.mocks["check_call"].call_count, 3)
        self.mocks["check_call"].assert_has_calls(
            self._add_ua_proxy_setup_calls(
                [
                    call(["add-apt-repository", "--yes", "ppa:ua-client/stable"], env=self.env),
                ]
            )
        )
        self._assert_apt_calls()
        self.assertEqual(self.harness.charm._state.ppa, "ppa:ua-client/stable")
        self.assertFalse(self.harness.charm._state.package_needs_installing)

    def test_config_changed_ppa_updated(self):
        self.mocks["run"].side_effect = [
            MagicMock(returncode=0, stdout=STATUS_DETACHED),
            MagicMock(returncode=0, stdout=STATUS_DETACHED),
        ]
        self.harness.update_config({"ppa": "ppa:ua-client/stable"})
        self.assertEqual(self.mocks["check_call"].call_count, 3)
        self.mocks["check_call"].assert_has_calls(
            self._add_ua_proxy_setup_calls(
                [
                    call(["add-apt-repository", "--yes", "ppa:ua-client/stable"], env=self.env),
                ]
            )
        )
        self._assert_apt_calls()
        self.assertEqual(self.harness.charm._state.ppa, "ppa:ua-client/stable")
        self.assertFalse(self.harness.charm._state.package_needs_installing)

        self.mocks["check_call"].reset_mock()
        self.mocks["apt"].reset_mock()
        self.harness.update_config({"ppa": "ppa:different-client/unstable"})
        self.assertEqual(self.mocks["check_call"].call_count, 4)
        self.mocks["check_call"].assert_has_calls(
            self._add_ua_proxy_setup_calls(
                [
                    call(
                        ["add-apt-repository", "--remove", "--yes", "ppa:ua-client/stable"],
                        env=self.env,
                    ),
                    call(
                        ["add-apt-repository", "--yes", "ppa:different-client/unstable"],
                        env=self.env,
                    ),
                ]
            )
        )
        self._assert_apt_calls()
        self.assertEqual(self.harness.charm._state.ppa, "ppa:different-client/unstable")
        self.assertFalse(self.harness.charm._state.package_needs_installing)

    def test_config_changed_ppa_unmodified(self):
        self.mocks["run"].side_effect = [
            MagicMock(returncode=0, stdout=STATUS_DETACHED),
            MagicMock(returncode=0, stdout=STATUS_DETACHED),
        ]
        self.harness.update_config({"ppa": "ppa:ua-client/stable"})
        self.assertEqual(self.mocks["check_call"].call_count, 3)
        self.mocks["check_call"].assert_has_calls(
            self._add_ua_proxy_setup_calls(
                [
                    call(["add-apt-repository", "--yes", "ppa:ua-client/stable"], env=self.env),
                ]
            )
        )
        self._assert_apt_calls()
        self.assertEqual(self.harness.charm._state.ppa, "ppa:ua-client/stable")
        self.assertFalse(self.harness.charm._state.package_needs_installing)

        self.mocks["check_call"].reset_mock()
        self.harness.update_config({"ppa": "ppa:ua-client/stable"})
        self.assertEqual(self.mocks["check_call"].call_count, 2)
        self.mocks["check_call"].assert_has_calls(self._add_ua_proxy_setup_calls([]))
        self.assertEqual(self.harness.charm._state.ppa, "ppa:ua-client/stable")
        self.assertFalse(self.harness.charm._state.package_needs_installing)

    def test_config_changed_ppa_unset(self):
        self.mocks["run"].side_effect = [
            MagicMock(returncode=0, stdout=STATUS_DETACHED),
            MagicMock(returncode=0, stdout=STATUS_DETACHED),
        ]
        self.harness.update_config({"ppa": "ppa:ua-client/stable"})
        self.assertEqual(self.mocks["check_call"].call_count, 3)
        self.mocks["check_call"].assert_has_calls(
            self._add_ua_proxy_setup_calls(
                [
                    call(["add-apt-repository", "--yes", "ppa:ua-client/stable"], env=self.env),
                ]
            )
        )
        self._assert_apt_calls()
        self.assertEqual(self.harness.charm._state.ppa, "ppa:ua-client/stable")
        self.assertFalse(self.harness.charm._state.package_needs_installing)

        self.mocks["check_call"].reset_mock()
        self.mocks["apt"].reset_mock()
        self.harness.update_config({"ppa": ""})
        self.assertEqual(self.mocks["check_call"].call_count, 3)
        self.mocks["check_call"].assert_has_calls(
            self._add_ua_proxy_setup_calls(
                [
                    call(
                        ["add-apt-repository", "--remove", "--yes", "ppa:ua-client/stable"],
                        env=self.env,
                    ),
                ]
            )
        )
        self._assert_apt_calls()
        self.assertIsNone(self.harness.charm._state.ppa)
        self.assertFalse(self.harness.charm._state.package_needs_installing)

    def test_config_changed_ppa_apt_failure(self):
        self.mocks["check_call"].side_effect = CalledProcessError(
            "apt failure", "add-apt-repository"
        )
        with self.assertRaises(CalledProcessError):
            self.harness.update_config({"ppa": "ppa:ua-client/stable"})
        self.assertIsNone(self.harness.charm._state.ppa)
        self.assertTrue(self.harness.charm._state.package_needs_installing)
        self.assertIsInstance(self.harness.model.unit.status, MaintenanceStatus)

    def test_config_changed_token_unattached(self):
        self.mocks["run"].side_effect = [
            MagicMock(returncode=0, stdout=bytes(STATUS_DETACHED, "utf-8")),
            MagicMock(returncode=0),
            MagicMock(returncode=0, stdout=bytes(STATUS_ATTACHED, "utf-8")),
        ]
        self.harness.update_config({"token": "test-token"})
        self.mocks["open"].assert_called_with("/etc/ubuntu-advantage/uaclient.conf", "r+")
        handle = self.mocks["open"]()
        expected = dedent(
            """\
            contract_url: https://contracts.canonical.com
            data_dir: /var/lib/ubuntu-advantage
            log_file: /var/log/ubuntu-advantage.log
            log_level: debug
        """
        )
        self.assertEqual(_written(handle), expected)
        handle.truncate.assert_called_once()
        self.assertEqual(self.mocks["run"].call_count, 3)
        self.mocks["run"].assert_has_calls(
            [call(["ubuntu-advantage", "attach", "test-token"], capture_output=True, text=True)]
        )
        self.assertEqual(
            self.harness.charm._state.hashed_token,
            "4c5dc9b7708905f77f5e5d16316b5dfb425e68cb326dcd55a860e90a7707031e",
        )
        self.assertEqual(
            self.harness.model.unit.status, ActiveStatus("Attached (esm-apps,esm-infra,livepatch)")
        )

    def test_config_changed_token_reattach(self):
        self.mocks["run"].side_effect = [
            MagicMock(returncode=0, stdout=bytes(STATUS_DETACHED, "utf-8")),
            MagicMock(returncode=0),
            MagicMock(returncode=0, stdout=bytes(STATUS_ATTACHED, "utf-8")),
        ]
        self.harness.update_config({"token": "test-token"})
        self.assertEqual(self.mocks["check_call"].call_count, 2)
        self._assert_apt_calls()
        self.mocks["open"].assert_called_with("/etc/ubuntu-advantage/uaclient.conf", "r+")
        self._assert_apt_calls()
        handle = self.mocks["open"]()
        expected = dedent(
            """\
            contract_url: https://contracts.canonical.com
            data_dir: /var/lib/ubuntu-advantage
            log_file: /var/log/ubuntu-advantage.log
            log_level: debug
        """
        )
        self.assertEqual(_written(handle), expected)
        handle.truncate.assert_called_once()
        # self.assertEqual(self.mocks["run"].call_count, 3)
        self.mocks["run"].assert_has_calls(
            [call(["ubuntu-advantage", "attach", "test-token"], capture_output=True, text=True)]
        )
        self.assertEqual(
            self.harness.charm._state.hashed_token,
            "4c5dc9b7708905f77f5e5d16316b5dfb425e68cb326dcd55a860e90a7707031e",
        )

        self.mocks["run"].reset_mock()
        self.mocks["check_call"].reset_mock()
        self.mocks["run"].side_effect = [
            MagicMock(returncode=0, stdout=bytes(STATUS_ATTACHED, "utf-8")),
            MagicMock(returncode=0),
            MagicMock(returncode=0, stdout=bytes(STATUS_ATTACHED, "utf-8")),
        ]
        self.harness.update_config({"token": "test-token-2"})
        self.assertEqual(self.mocks["check_call"].call_count, 3)
        self.mocks["check_call"].assert_has_calls(
            self._add_ua_proxy_setup_calls(
                [call(["ubuntu-advantage", "detach", "--assume-yes"])], append=False
            )
        )
        self.assertEqual(self.mocks["run"].call_count, 3)
        self.mocks["run"].assert_has_calls(
            [call(["ubuntu-advantage", "attach", "test-token-2"], capture_output=True, text=True)]
        )
        self.assertEqual(
            self.harness.charm._state.hashed_token,
            "ab8a83efb364bf3f6739348519b53c8e8e0f7b4c06b6eeb881ad73dcf0059107",
        )
        self.assertEqual(
            self.harness.model.unit.status, ActiveStatus("Attached (esm-apps,esm-infra,livepatch)")
        )

    def test_config_changed_attach_failure(self):
        self.mocks["run"].side_effect = [
            # Call 1 to status
            # Call 2 to attach
            MagicMock(returncode=0, stdout=STATUS_DETACHED),
            MagicMock(returncode=1, stderr="Invalid token"),
        ]
        self.harness.update_config({"token": "test-token"})
        message = "Error attaching: Invalid token"
        self.assertEqual(self.harness.model.unit.status, BlockedStatus(message))

    def test_config_changed_token_detach(self):
        self.mocks["run"].side_effect = [
            MagicMock(returncode=0, stdout=bytes(STATUS_ATTACHED, "utf-8")),
            MagicMock(returncode=0),
            MagicMock(returncode=0, stdout=bytes(STATUS_ATTACHED, "utf-8")),
        ]
        self.harness.update_config({"token": "test-token"})
        self.assertEqual(self.mocks["run"].call_count, 3)
        self.mocks["run"].assert_has_calls(
            [call(["ubuntu-advantage", "attach", "test-token"], capture_output=True, text=True)]
        )
        self.assertEqual(
            self.harness.charm._state.hashed_token,
            "4c5dc9b7708905f77f5e5d16316b5dfb425e68cb326dcd55a860e90a7707031e",
        )

        self.mocks["run"].reset_mock()
        self.mocks["check_call"].reset_mock()
        self.mocks["run"].side_effect = [
            MagicMock(returncode=0, stdout=bytes(STATUS_ATTACHED, "utf-8")),
            MagicMock(returncode=0, stdout=bytes(STATUS_DETACHED, "utf-8")),
        ]
        self.harness.update_config({"token": ""})
        self.assertEqual(self.mocks["check_call"].call_count, 3)
        self.mocks["check_call"].assert_has_calls(
            self._add_ua_proxy_setup_calls(
                [call(["ubuntu-advantage", "detach", "--assume-yes"])], append=False
            )
        )
        self.assertIsNone(self.harness.charm._state.hashed_token)
        self.assertEqual(self.harness.model.unit.status, BlockedStatus("No token configured"))

    def test_config_changed_token_update_after_block(self):
        # initial call to status mock
        self.mocks["run"].side_effect = [MagicMock(returncode=0, stdout=STATUS_DETACHED)]
        self.harness.update_config()
        self.assertIsInstance(self.harness.model.unit.status, BlockedStatus)

        # subsequent calls to status and attach mocked
        self.mocks["run"].reset_mock()
        self.mocks["run"].side_effect = [
            MagicMock(returncode=0, stdout=bytes(STATUS_DETACHED, "utf-8")),
            MagicMock(returncode=0),
            MagicMock(returncode=0, stdout=bytes(STATUS_ATTACHED, "utf-8")),
        ]
        self.harness.update_config({"token": "test-token"})
        self.assertEqual(self.mocks["run"].call_count, 3)
        self.mocks["run"].assert_has_calls(
            [call(["ubuntu-advantage", "attach", "test-token"], capture_output=True, text=True)]
        )
        self.assertIsInstance(self.harness.model.unit.status, ActiveStatus)

    def test_config_changed_token_contains_newline(self):
        self.mocks["run"].side_effect = [
            MagicMock(returncode=0, stdout=bytes(STATUS_DETACHED, "utf-8")),
            MagicMock(returncode=0),
            MagicMock(returncode=0, stdout=bytes(STATUS_ATTACHED, "utf-8")),
        ]
        self.harness.update_config({"token": "test-token\n"})
        self.mocks["run"].assert_has_calls(
            [call(["ubuntu-advantage", "attach", "test-token"], capture_output=True, text=True)]
        )
        self.assertEqual(
            self.harness.charm._state.hashed_token,
            "4c5dc9b7708905f77f5e5d16316b5dfb425e68cb326dcd55a860e90a7707031e",
        )

    def test_config_changed_ppa_contains_newline(self):
        self.mocks["run"].return_value = MagicMock(returncode=0, stdout=STATUS_DETACHED)
        self.harness.update_config({"ppa": "ppa:ua-client/stable\n"})
        self.mocks["check_call"].assert_has_calls(
            [
                call(["add-apt-repository", "--yes", "ppa:ua-client/stable"], env=self.env),
            ]
        )
        self.assertEqual(self.harness.charm._state.ppa, "ppa:ua-client/stable")

    def test_config_changed_check_output_returns_bytes(self):
        self.mocks["run"].side_effect = [
            MagicMock(returncode=0, stdout=bytes(STATUS_DETACHED, "utf-8")),
            MagicMock(returncode=0),
            MagicMock(returncode=0, stdout=bytes(STATUS_ATTACHED, "utf-8")),
        ]
        self.harness.update_config({"token": "test-token"})
        self.assertEqual(
            self.harness.model.unit.status, ActiveStatus("Attached (esm-apps,esm-infra,livepatch)")
        )

    def test_config_changed_contract_url(self):
        self.mocks["run"].side_effect = [
            MagicMock(returncode=0, stdout=bytes(STATUS_DETACHED, "utf-8")),
            MagicMock(returncode=0),
            MagicMock(returncode=0, stdout=bytes(STATUS_ATTACHED, "utf-8")),
        ]
        self.harness.update_config({"contract_url": "https://contracts.staging.canonical.com"})
        self.mocks["open"].assert_called_with("/etc/ubuntu-advantage/uaclient.conf", "r+")
        handle = self.mocks["open"]()
        expected = dedent(
            """\
            contract_url: https://contracts.staging.canonical.com
            data_dir: /var/lib/ubuntu-advantage
            log_file: /var/log/ubuntu-advantage.log
            log_level: debug
        """
        )
        self.assertEqual(_written(handle), expected)
        handle.truncate.assert_called_once()
        self.assertEqual(
            self.harness.charm._state.contract_url, "https://contracts.staging.canonical.com"
        )

    def test_config_changed_contract_url_reattach(self):
        self.mocks["run"].side_effect = [
            MagicMock(returncode=0, stdout=bytes(STATUS_DETACHED, "utf-8")),
            MagicMock(returncode=0),
            MagicMock(returncode=0, stdout=bytes(STATUS_ATTACHED, "utf-8")),
        ]
        self.harness.update_config({"token": "test-token"})
        self.mocks["run"].assert_has_calls(
            [call(["ubuntu-advantage", "attach", "test-token"], capture_output=True, text=True)]
        )
        self.assertEqual(
            self.harness.charm._state.hashed_token,
            "4c5dc9b7708905f77f5e5d16316b5dfb425e68cb326dcd55a860e90a7707031e",
        )

        self.mocks["run"].reset_mock()
        self.mocks["check_call"].reset_mock()
        self.mocks["open"].reset_mock()
        self.mocks["run"].side_effect = [
            MagicMock(returncode=0, stdout=bytes(STATUS_ATTACHED, "utf-8")),
            MagicMock(returncode=0),
            MagicMock(returncode=0, stdout=bytes(STATUS_ATTACHED, "utf-8")),
        ]
        mock_open(self.mocks["open"], read_data=DEFAULT_CLIENT_CONFIG)
        self.harness.update_config({"contract_url": "https://contracts.staging.canonical.com"})
        self.mocks["open"].assert_called_with("/etc/ubuntu-advantage/uaclient.conf", "r+")
        handle = self.mocks["open"]()
        expected = dedent(
            """\
            contract_url: https://contracts.staging.canonical.com
            data_dir: /var/lib/ubuntu-advantage
            log_file: /var/log/ubuntu-advantage.log
            log_level: debug
        """
        )
        self.assertEqual(_written(handle), expected)
        handle.truncate.assert_called_once()
        self.mocks["check_call"].assert_has_calls(
            [call(["ubuntu-advantage", "detach", "--assume-yes"])]
        )
        self.mocks["run"].assert_has_calls(
            [call(["ubuntu-advantage", "attach", "test-token"], capture_output=True, text=True)]
        )
        self.assertEqual(
            self.harness.model.unit.status, ActiveStatus("Attached (esm-apps,esm-infra,livepatch)")
        )

        self.mocks["run"].reset_mock()
        self.mocks["check_call"].reset_mock()
        self.mocks["open"].reset_mock()
        self.mocks["run"].side_effect = [
            MagicMock(returncode=0, stdout=bytes(STATUS_ATTACHED, "utf-8")),
            MagicMock(returncode=0, stdout=bytes(STATUS_ATTACHED, "utf-8")),
        ]
        mock_open(self.mocks["open"], read_data=DEFAULT_CLIENT_CONFIG)
        self.harness.update_config()
        self.mocks["open"].assert_not_called()

    def test_config_changed_unset_contract_url(self):
        self.mocks["run"].side_effect = [
            MagicMock(returncode=0, stdout=bytes(STATUS_DETACHED, "utf-8")),
            MagicMock(returncode=0),
            MagicMock(returncode=0, stdout=bytes(STATUS_ATTACHED, "utf-8")),
        ]
        self.harness.update_config({"contract_url": "https://contracts.staging.canonical.com"})
        self.mocks["open"].assert_called_with("/etc/ubuntu-advantage/uaclient.conf", "r+")
        handle = self.mocks["open"]()
        expected = dedent(
            """\
            contract_url: https://contracts.staging.canonical.com
            data_dir: /var/lib/ubuntu-advantage
            log_file: /var/log/ubuntu-advantage.log
            log_level: debug
        """
        )
        self.assertEqual(_written(handle), expected)
        handle.truncate.assert_called_once()
        self.mocks["call"].assert_not_called()
        self.assertEqual(self.harness.model.unit.status, BlockedStatus("No token configured"))
        self.mocks["open"].reset_mock()
        self.mocks["call"].reset_mock()
        self.mocks["check_call"].reset_mock()
        self.mocks["run"].reset_mock()
        self.mocks["run"].side_effect = [
            MagicMock(returncode=0, stdout=bytes(STATUS_DETACHED, "utf-8")),
            MagicMock(returncode=0),
            MagicMock(returncode=0, stdout=bytes(STATUS_ATTACHED, "utf-8")),
        ]
        self.harness.update_config({"contract_url": "https://contracts.canonical.com"})
        self.mocks["open"].assert_called_with("/etc/ubuntu-advantage/uaclient.conf", "r+")
        handle = self.mocks["open"]()
        expected = dedent(
            """\
            contract_url: https://contracts.canonical.com
            data_dir: /var/lib/ubuntu-advantage
            log_file: /var/log/ubuntu-advantage.log
            log_level: debug
        """
        )
        self.assertEqual(_written(handle), expected)
        handle.truncate.assert_called_once()
        self.mocks["call"].assert_not_called()
        self.assertEqual(self.harness.model.unit.status, BlockedStatus("No token configured"))

    def test_config_changed_set_and_unset_proxy_override(self):
        # Set proxy override once.
        self.mocks["run"].side_effect = [MagicMock(returncode=0, stdout=STATUS_DETACHED)]
        self.harness.update_config(
            {
                "override-http-proxy": "http://localhost:3128",
                "override-https-proxy": "http://localhost:3128",
            }
        )
        self.mocks["check_call"].assert_has_calls(
            [
                call(["ubuntu-advantage", "config", "set", "http_proxy=http://localhost:3128"]),
                call(["ubuntu-advantage", "config", "set", "https_proxy=http://localhost:3128"]),
            ]
        )
        self.mocks["check_call"].reset_mock()

        # Set proxy override again.
        self.mocks["run"].side_effect = [MagicMock(returncode=0, stdout=STATUS_DETACHED)]
        self.harness.update_config(
            {
                "override-http-proxy": "http://squid.internal:3128",
                "override-https-proxy": "http://squid.internal:3128",
            }
        )
        self.mocks["check_call"].assert_has_calls(
            [
                call(
                    ["ubuntu-advantage", "config", "set", "http_proxy=http://squid.internal:3128"]
                ),
                call(
                    ["ubuntu-advantage", "config", "set", "https_proxy=http://squid.internal:3128"]
                ),
            ]
        )
        self.mocks["check_call"].reset_mock()

        # Unset proxy override.
        self.mocks["run"].side_effect = [MagicMock(returncode=0, stdout=STATUS_DETACHED)]
        self.harness.update_config({"override-http-proxy": "", "override-https-proxy": ""})
        self.mocks["check_call"].assert_has_calls(
            [
                call(["ubuntu-advantage", "config", "unset", "http_proxy"]),
                call(["ubuntu-advantage", "config", "unset", "https_proxy"]),
            ]
        )

    def test_setup_proxy_config(self):
        self.mocks["run"].side_effect = [MagicMock(returncode=0, stdout=STATUS_DETACHED)]
        self.harness.update_config(
            {
                "override-http-proxy": TEST_PROXY_URL,
                "override-https-proxy": TEST_PROXY_URL,
            }
        )

        self.harness.charm._setup_proxy_env()
        self.assertEqual(self.harness.charm.env["http_proxy"], TEST_PROXY_URL)
        self.assertEqual(self.harness.charm.env["https_proxy"], TEST_PROXY_URL)

    def test_setup_proxy_env(self):
        self.mocks["environ"].update(
            {
                "JUJU_CHARM_HTTP_PROXY": TEST_PROXY_URL,
                "JUJU_CHARM_HTTPS_PROXY": TEST_PROXY_URL,
                "JUJU_CHARM_NO_PROXY": TEST_NO_PROXY,
            }
        )

        self.harness.charm._setup_proxy_env()
        self.assertEqual(self.harness.charm.env["http_proxy"], TEST_PROXY_URL)
        self.assertEqual(self.harness.charm.env["https_proxy"], TEST_PROXY_URL)
        self.assertEqual(self.harness.charm.env["no_proxy"], TEST_NO_PROXY)

    def _add_ua_proxy_setup_calls(self, call_list, append=True):
        """Helper to generate the calls used for UA proxy setup."""
        proxy_calls = []
        if self.env["http_proxy"]:
            proxy_calls.append(
                call(
                    [
                        "ubuntu-advantage",
                        "config",
                        "set",
                        "http_proxy={}".format(self.env["http_proxy"]),
                    ]
                )
            )
        else:
            proxy_calls.append(
                call(
                    [
                        "ubuntu-advantage",
                        "config",
                        "unset",
                        "http_proxy",
                    ]
                )
            )

        if self.env["https_proxy"]:
            proxy_calls.append(
                call(
                    [
                        "ubuntu-advantage",
                        "config",
                        "set",
                        "https_proxy={}".format(self.env["https_proxy"]),
                    ]
                )
            )
        else:
            proxy_calls.append(
                call(
                    [
                        "ubuntu-advantage",
                        "config",
                        "unset",
                        "https_proxy",
                    ]
                )
            )

        return call_list + proxy_calls if append else proxy_calls + call_list

    def _assert_apt_calls(self):
        """Helper to run the assertions for apt install."""
        self.mocks["apt"].add_package.assert_called_once_with(
            "ubuntu-advantage-tools", update_cache=True
        )
