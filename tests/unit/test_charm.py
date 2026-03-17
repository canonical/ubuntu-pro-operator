# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import tempfile
from pathlib import Path
from subprocess import PIPE, CalledProcessError
from textwrap import dedent
from unittest import TestCase
from unittest.mock import ANY, MagicMock, call, mock_open, patch

import pytest
import yaml
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus
from ops.testing import Harness

from charm import UbuntuAdvantageCharm, remove_configuration, update_configuration
from exceptions import ProcessExecutionError

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
            "status_output": patch("charm.get_status_output").start(),
            "install_livepatch": patch("charm.install_livepatch").start(),
            "disable_livepatch": patch("charm.disable_canonical_livepatch").start(),
        }
        self.mocks["call"].return_value = 0
        self.mocks["run"].return_value = MagicMock(returncode=0, stderr="")
        self.mocks["status_output"].return_value = json.loads(STATUS_DETACHED)
        mock_open(self.mocks["open"], read_data=DEFAULT_CLIENT_CONFIG)
        self.harness = Harness(UbuntuAdvantageCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()
        self.proxy_env = self.harness.charm.proxy_env

    def test_config_defaults(self):
        self.assertEqual(
            self.harness.charm.config.get("contract_url"), "https://contracts.canonical.com"
        )
        self.assertEqual(self.harness.charm.config.get("ppa"), "")
        self.assertEqual(self.harness.charm.config.get("token"), "")
        self.assertEqual(self.harness.charm.config.get("security_url"), "")

    def test_config_changed_ppa_new(self):
        self.harness.update_config({"ppa": "ppa:ua-client/stable"})
        self.mocks["check_call"].assert_has_calls(
            self._add_ua_proxy_setup_calls(
                [
                    call(
                        ["add-apt-repository", "--yes", "ppa:ua-client/stable"], env=self.proxy_env
                    ),
                ]
            )
        )
        self._assert_apt_calls()
        self.assertEqual(self.harness.charm._state.ppa, "ppa:ua-client/stable")
        self.assertFalse(self.harness.charm._state.package_needs_installing)

    def test_config_changed_ppa_updated(self):
        self.harness.update_config({"ppa": "ppa:ua-client/stable"})
        self.mocks["check_call"].assert_has_calls(
            self._add_ua_proxy_setup_calls(
                [
                    call(
                        ["add-apt-repository", "--yes", "ppa:ua-client/stable"], env=self.proxy_env
                    ),
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
                        env=self.proxy_env,
                    ),
                    call(
                        ["add-apt-repository", "--yes", "ppa:different-client/unstable"],
                        env=self.proxy_env,
                    ),
                ]
            )
        )
        self._assert_apt_calls()
        self.assertEqual(self.harness.charm._state.ppa, "ppa:different-client/unstable")
        self.assertFalse(self.harness.charm._state.package_needs_installing)

    def test_config_changed_ppa_unmodified(self):
        self.harness.update_config({"ppa": "ppa:ua-client/stable"})
        self.mocks["check_call"].assert_has_calls(
            self._add_ua_proxy_setup_calls(
                [
                    call(
                        ["add-apt-repository", "--yes", "ppa:ua-client/stable"], env=self.proxy_env
                    ),
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
        self.harness.update_config({"ppa": "ppa:ua-client/stable"})
        self.mocks["check_call"].assert_has_calls(
            self._add_ua_proxy_setup_calls(
                [
                    call(
                        ["add-apt-repository", "--yes", "ppa:ua-client/stable"], env=self.proxy_env
                    ),
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
                        env=self.proxy_env,
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

    @patch("charm.attach", side_effect=[(0, "")])
    @patch(
        "charm.get_status_output",
        side_effect=[
            json.loads(STATUS_ATTACHED),
        ],
    )
    def test_config_changed_token_unattached(self, m_get_status_output, m_attach):
        self.harness.update_config({"token": "test-token"})
        self.mocks["open"].assert_called_with("/etc/ubuntu-advantage/uaclient.conf", "r+")
        handle = self.mocks["open"]()
        written = _written(handle)

        assert "contract_url: https://contracts.canonical.com" in written
        assert "data_dir: /var/lib/ubuntu-advantage" in written
        assert "log_file: /var/log/ubuntu-advantage.log" in written
        assert "log_level: debug" in written
        assert m_get_status_output.call_count == 1
        assert m_attach.call_count == 1
        self.assertEqual(
            self.harness.charm._state.hashed_token,
            "4c5dc9b7708905f77f5e5d16316b5dfb425e68cb326dcd55a860e90a7707031e",
        )
        self.assertEqual(
            self.harness.model.unit.status, ActiveStatus("Attached (esm-apps,esm-infra,livepatch)")
        )

    @patch("charm.attach", side_effect=[(0, ""), (0, "")])
    @patch(
        "charm.get_status_output",
        side_effect=[
            json.loads(STATUS_ATTACHED),
            json.loads(STATUS_ATTACHED),
        ],
    )
    def test_config_changed_token_reattach(self, m_get_status_output, m_attach):
        self.harness.update_config({"token": "test-token"})
        self._assert_apt_calls()
        self.mocks["open"].assert_called_with("/etc/ubuntu-advantage/uaclient.conf", "r+")
        self._assert_apt_calls()
        handle = self.mocks["open"]()
        written = _written(handle)

        assert "contract_url: https://contracts.canonical.com" in written
        assert "data_dir: /var/lib/ubuntu-advantage" in written
        assert "log_file: /var/log/ubuntu-advantage.log" in written
        assert "log_level: debug" in written
        assert m_get_status_output.call_count == 1
        assert m_attach.call_count == 1
        self.assertEqual(
            self.harness.charm._state.hashed_token,
            "4c5dc9b7708905f77f5e5d16316b5dfb425e68cb326dcd55a860e90a7707031e",
        )

        self.mocks["check_call"].reset_mock()
        self.harness.update_config({"token": "test-token-2"})
        self.assertEqual(self.mocks["check_call"].call_count, 2)
        self.mocks["check_call"].assert_has_calls(self._add_ua_proxy_setup_calls([]))
        assert m_get_status_output.call_count == 2
        assert m_attach.call_count == 2
        self.assertEqual(
            self.harness.charm._state.hashed_token,
            "ab8a83efb364bf3f6739348519b53c8e8e0f7b4c06b6eeb881ad73dcf0059107",
        )
        self.assertEqual(
            self.harness.model.unit.status, ActiveStatus("Attached (esm-apps,esm-infra,livepatch)")
        )

    @patch(
        "charm.get_status_output",
        side_effect=[
            json.loads(STATUS_DETACHED),
            json.loads(STATUS_ATTACHED),
        ],
    )
    def test_attach_retry_on_failure(self, m_get_status_output):
        self.mocks["run"].side_effect = [
            MagicMock(returncode=0, stderr=""),
            ProcessExecutionError("attach", 1, "", "Invalid token"),
            MagicMock(returncode=0, stderr=""),
        ]
        self.harness.update_config({"token": "test-token"})
        self.assertEqual(self.mocks["run"].call_count, 1)
        self.assertEqual(m_get_status_output.call_count, 2)
        self.assertEqual(
            self.harness.model.unit.status, ActiveStatus("Attached (esm-apps,esm-infra,livepatch)")
        )

    @patch(
        "charm.attach",
        side_effect=[ProcessExecutionError("attach", 1, "", "Invalid token")],
    )
    def test_config_changed_attach_failure(self, m_attach):
        self.harness.update_config({"token": "test-token"})
        assert self.mocks["status_output"].call_count == 0
        assert m_attach.call_count == 1
        message = (
            "Failed running command 'attach' [exit status: 1].\nstderr: Invalid token\nstdout: "
        )
        self.assertEqual(self.harness.model.unit.status, BlockedStatus(message))

    @patch("charm.parse_services")
    @patch("charm.create_attach_config")
    def test_attach_with_added_services(self, m_create_attach_config, m_parse_services):
        m_parse_services.return_value = ["esm-infra", "fips"]
        m_create_attach_config.return_value.__enter__.return_value = "/tmp/mock_attach.yaml"
        self.harness.update_config({"token": "test-token", "services": "esm-infra, fips"})

        m_parse_services.assert_called_once_with("esm-infra, fips")
        assert m_create_attach_config.call_count == 1

    @patch("charm.attach", return_value=(0, ""))
    def test_attach_with_no_services(self, m_attach):
        self.harness.update_config({"token": "test-token"})
        m_attach.assert_called_once_with("test-token", ANY, services=None)

    @patch(
        "charm.get_status_output",
        side_effect=[
            json.loads(STATUS_ATTACHED),
            json.loads(STATUS_ATTACHED),
        ],
    )
    @patch("charm.attach", side_effect=[(0, "")])
    def test_config_changed_token_detach(self, m_attach, m_get_status_output):
        self.harness.update_config({"token": "test-token"})
        self.assertEqual(
            self.harness.charm._state.hashed_token,
            "4c5dc9b7708905f77f5e5d16316b5dfb425e68cb326dcd55a860e90a7707031e",
        )

        self.mocks["check_call"].reset_mock()
        self.harness.update_config({"token": ""})
        self.assertEqual(self.mocks["check_call"].call_count, 3)
        self.mocks["check_call"].assert_has_calls(
            self._add_ua_proxy_setup_calls(
                [call(["ubuntu-advantage", "detach", "--assume-yes"], env=ANY)], append=False
            )
        )
        assert m_get_status_output.call_count == 2
        assert m_attach.call_count == 1
        self.assertIsNone(self.harness.charm._state.hashed_token)
        self.assertEqual(self.harness.model.unit.status, BlockedStatus("No token configured"))

    @patch("charm.attach", side_effect=[(0, "")])
    @patch(
        "charm.get_status_output",
        side_effect=[
            json.loads(STATUS_DETACHED),
            json.loads(STATUS_ATTACHED),
        ],
    )
    def test_config_changed_token_update_after_block(self, m_get_status_output, m_attach):
        self.harness.update_config()
        self.assertIsInstance(self.harness.model.unit.status, BlockedStatus)

        self.harness.update_config({"token": "test-token"})
        assert m_get_status_output.call_count == 2
        assert m_attach.call_count == 1
        self.assertIsInstance(self.harness.model.unit.status, ActiveStatus)

    @patch("charm.attach", side_effect=[(0, "")])
    @patch(
        "charm.get_status_output",
        side_effect=[
            json.loads(STATUS_DETACHED),
            json.loads(STATUS_DETACHED),
            json.loads(STATUS_ATTACHED),
        ],
    )
    def test_config_changed_token_contains_newline(self, m_get_status_output, m_attach):
        self.harness.update_config({"token": "test-token\n"})
        self.assertEqual(
            self.harness.charm._state.hashed_token,
            "4c5dc9b7708905f77f5e5d16316b5dfb425e68cb326dcd55a860e90a7707031e",
        )
        assert m_get_status_output.call_count == 1
        assert m_attach.call_count == 1

    def test_config_changed_ppa_contains_newline(self):
        self.harness.update_config({"ppa": "ppa:ua-client/stable\n"})
        self.mocks["check_call"].assert_has_calls(
            [
                call(["add-apt-repository", "--yes", "ppa:ua-client/stable"], env=self.proxy_env),
            ]
        )
        self.assertEqual(self.harness.charm._state.ppa, "ppa:ua-client/stable")
        assert self.mocks["status_output"].call_count == 1

    @patch("charm.attach", side_effect=[(0, "")])
    @patch(
        "charm.get_status_output",
        side_effect=[
            json.loads(bytes(STATUS_ATTACHED, "utf-8")),
        ],
    )
    def test_config_changed_check_output_returns_bytes(self, m_get_status_output, m_attach):
        self.harness.update_config({"token": "test-token"})
        self.assertEqual(
            self.harness.model.unit.status, ActiveStatus("Attached (esm-apps,esm-infra,livepatch)")
        )

    def test_config_changed_security_url(self):
        """If the security_url is set to a new value, update it."""
        new_url = "https://offline.ubuntu.com/security"
        self.assertNotEqual(new_url, self.harness.charm.config["security_url"])
        self.harness.update_config({"security_url": new_url})
        self.mocks["open"].assert_called_with("/etc/ubuntu-advantage/uaclient.conf", "r+")
        handle = self.mocks["open"]()
        written = _written(handle)
        assert "security_url: https://offline.ubuntu.com/security" in written

    def test_config_changed_vulnerability_data_url_prefix(self):
        """If the vulnerability_data_url_prefix is set to a new value, update it under ua_config."""
        new_url = "https://example.com/cve-data"
        self.harness.update_config({"vulnerability_data_url_prefix": new_url})
        self.mocks["open"].assert_called_with("/etc/ubuntu-advantage/uaclient.conf", "r+")
        handle = self.mocks["open"]()
        written = _written(handle)
        assert "vulnerability_data_url_prefix: https://example.com/cve-data" in written
        assert "ua_config:" in written

    def test_config_changed_apt_news_url(self):
        """If the apt_news_url is set to a new value, update it under ua_config."""
        new_url = "https://example.com/apt-news"
        self.harness.update_config({"apt_news_url": new_url})
        self.mocks["open"].assert_called_with("/etc/ubuntu-advantage/uaclient.conf", "r+")
        handle = self.mocks["open"]()
        written = _written(handle)
        assert "apt_news_url: https://example.com/apt-news" in written
        assert "ua_config:" in written

    def test_config_changed_contract_url(self):
        self.harness.update_config({"contract_url": "https://contracts.staging.canonical.com"})
        self.mocks["open"].assert_called_with("/etc/ubuntu-advantage/uaclient.conf", "r+")
        handle = self.mocks["open"]()
        written = _written(handle)
        assert "contract_url: https://contracts.staging.canonical.com" in written
        assert "data_dir: /var/lib/ubuntu-advantage" in written
        assert "log_file: /var/log/ubuntu-advantage.log" in written
        assert "log_level: debug" in written
        assert "security_url" not in written
        assert self.mocks["status_output"].call_count == 1
        self.assertEqual(
            self.harness.charm._state.contract_url, "https://contracts.staging.canonical.com"
        )

    @patch("charm.attach", side_effect=[(0, ""), (0, "")])
    @patch(
        "charm.get_status_output",
        side_effect=[
            json.loads(STATUS_DETACHED),
            json.loads(STATUS_ATTACHED),
            json.loads(STATUS_ATTACHED),
            json.loads(STATUS_ATTACHED),
            json.loads(STATUS_ATTACHED),
            json.loads(STATUS_ATTACHED),
        ],
    )
    def test_config_changed_contract_url_reattach(self, m_get_status_output, m_attach):
        self.harness.update_config({"token": "test-token"})
        self.assertEqual(
            self.harness.charm._state.hashed_token,
            "4c5dc9b7708905f77f5e5d16316b5dfb425e68cb326dcd55a860e90a7707031e",
        )
        self.mocks["check_call"].reset_mock()
        self.mocks["open"].reset_mock()
        mock_open(self.mocks["open"], read_data=DEFAULT_CLIENT_CONFIG)
        self.harness.update_config({"contract_url": "https://contracts.staging.canonical.com"})
        self.mocks["open"].assert_called_with("/etc/ubuntu-advantage/uaclient.conf", "r+")
        handle = self.mocks["open"]()
        expected = dedent("""\
            contract_url: https://contracts.staging.canonical.com
            data_dir: /var/lib/ubuntu-advantage
            log_file: /var/log/ubuntu-advantage.log
            log_level: debug
        """)
        self.assertEqual(_written(handle), expected)
        handle.truncate.assert_called_once()
        self.mocks["check_call"].assert_has_calls(self._add_ua_proxy_setup_calls([]))
        self.assertEqual(
            self.harness.model.unit.status, ActiveStatus("Attached (esm-apps,esm-infra,livepatch)")
        )

        self.mocks["check_call"].reset_mock()
        self.mocks["open"].reset_mock()
        mock_open(self.mocks["open"], read_data=DEFAULT_CLIENT_CONFIG)
        self.harness.update_config()
        self.mocks["open"].assert_not_called()
        assert m_get_status_output.call_count == 3
        assert m_attach.call_count == 2

    @patch(
        "charm.get_status_output",
        side_effect=[
            json.loads(STATUS_DETACHED),
            json.loads(STATUS_ATTACHED),
        ],
    )
    def test_config_changed_unset_contract_url(self, m_get_status_output):
        self.harness.update_config({"contract_url": "https://contracts.staging.canonical.com"})
        self.mocks["open"].assert_called_with("/etc/ubuntu-advantage/uaclient.conf", "r+")
        handle = self.mocks["open"]()
        written = _written(handle)
        assert "contract_url: https://contracts.staging.canonical.com" in written
        assert "data_dir: /var/lib/ubuntu-advantage" in written
        assert "log_file: /var/log/ubuntu-advantage.log" in written
        assert "log_level: debug" in written
        self.mocks["call"].assert_not_called()
        self.assertEqual(self.harness.model.unit.status, BlockedStatus("No token configured"))
        self.mocks["open"].reset_mock()
        self.mocks["call"].reset_mock()
        self.mocks["check_call"].reset_mock()
        self.harness.update_config({"contract_url": "https://contracts.canonical.com"})
        self.mocks["open"].assert_called_with("/etc/ubuntu-advantage/uaclient.conf", "r+")
        handle = self.mocks["open"]()
        expected = dedent("""\
            contract_url: https://contracts.canonical.com
            data_dir: /var/lib/ubuntu-advantage
            log_file: /var/log/ubuntu-advantage.log
            log_level: debug
        """)
        assert m_get_status_output.call_count == 2
        self.assertEqual(_written(handle), expected)
        handle.truncate.assert_called_once()
        self.mocks["call"].assert_not_called()
        self.assertEqual(self.harness.model.unit.status, BlockedStatus("No token configured"))

    def test_config_changed_set_and_unset_proxy_override(self):
        # Set proxy override once.
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
        self.harness.update_config({"override-http-proxy": "", "override-https-proxy": ""})
        self.mocks["check_call"].assert_has_calls(
            [
                call(["ubuntu-advantage", "config", "unset", "http_proxy"]),
                call(["ubuntu-advantage", "config", "unset", "https_proxy"]),
            ]
        )

    def test_config_changed_set_ssl_cert_file_override(self):
        # Set proxy override once.
        self.harness.update_config(
            {
                "override-ssl-cert-file": "/etc/ssl/certs/ca-certificates.crt",
            }
        )
        self.mocks["run"].reset_mock()
        self.harness.update_config(
            {
                "token": "token",
            }
        )
        self.mocks["run"].assert_has_calls(
            [
                call(
                    ["ubuntu-advantage", "attach", "--attach-config", ANY],
                    stdout=PIPE,
                    stderr=PIPE,
                    env={"SSL_CERT_FILE": "/etc/ssl/certs/ca-certificates.crt"},
                ),
            ]
        )
        self.mocks["run"].reset_mock()

    @patch("charm.set_livepatch_server", side_effect=[(0, "")])
    @patch("charm.enable_livepatch_server", side_effect=[(0, "")])
    def test_canonical_livepatch_no_token(self, m_enable_livepatch_server, m_set_livepatch_server):
        self.assertFalse(self.harness.charm._state.livepatch_installed)
        self.harness.update_config({"livepatch_server_url": "https://www.example.com"})
        self.assertFalse(self.harness.charm._state.livepatch_installed)
        self.assertEqual(m_enable_livepatch_server.call_count, 0)
        self.assertEqual(m_set_livepatch_server.call_count, 0)
        self.assertEqual(self.mocks["install_livepatch"].call_count, 0)

    @patch("charm.get_enabled_services", side_effect=[["esm-apps", "esm-infra", "livepatch"]])
    @patch("charm.set_livepatch_server", side_effect=[(0, ""), (0, "")])
    @patch("charm.enable_livepatch_server", side_effect=[(0, "")])
    @patch("charm.get_status_output", return_value=json.loads(STATUS_ATTACHED))
    def test_canonical_livepatch_unset_server_livepatch_enabled(
        self,
        m_get_status_output,
        m_enable_livepatch_server,
        m_set_livepatch_server,
        m_get_enabled_services,
    ):
        self.harness.update_config(
            {"livepatch_server_url": "https://www.example.com", "livepatch_token": "new-token"}
        )
        self.mocks["check_call"].reset_mock()
        self.harness.update_config({"livepatch_server_url": "", "livepatch_token": ""})
        self.assertEqual(self.mocks["install_livepatch"].call_count, 1)
        self.assertEqual(self.mocks["disable_livepatch"].call_count, 2)
        self.assertEqual(m_enable_livepatch_server.call_count, 1)
        self.assertEqual(m_set_livepatch_server.call_count, 2)
        self.assertEqual(m_get_enabled_services.call_count, 1)
        self.mocks["check_call"].assert_has_calls(
            [call(["ubuntu-advantage", "enable", "livepatch"], env=ANY)]
        )

    @patch("charm.get_enabled_services", side_effect=[[]])
    @patch("charm.set_livepatch_server", side_effect=[(0, ""), (0, "")])
    @patch("charm.enable_livepatch_server", side_effect=[(0, "")])
    def test_canonical_livepatch_unset_server_unattached(
        self, m_enable_livepatch_server, m_set_livepatch_server, m_get_enabled_services
    ):
        self.harness.update_config(
            {"livepatch_server_url": "https://www.example.com", "livepatch_token": "new-token"}
        )
        self.assertTrue(self.harness.charm._state.livepatch_installed)
        self.harness.update_config({"livepatch_server_url": "", "livepatch_token": ""})
        self.assertEqual(self.mocks["install_livepatch"].call_count, 1)
        self.assertEqual(self.mocks["disable_livepatch"].call_count, 2)
        self.assertEqual(m_enable_livepatch_server.call_count, 1)
        self.assertEqual(m_set_livepatch_server.call_count, 2)
        self.assertEqual(m_get_enabled_services.call_count, 1)

    def test_setup_proxy_config(self):
        self.harness.update_config(
            {
                "override-http-proxy": TEST_PROXY_URL,
                "override-https-proxy": TEST_PROXY_URL,
            }
        )

        self.harness.charm._setup_proxy_env()
        self.assertEqual(self.harness.charm.proxy_env["http_proxy"], TEST_PROXY_URL)
        self.assertEqual(self.harness.charm.proxy_env["https_proxy"], TEST_PROXY_URL)

    def test_setup_proxy_env(self):
        self.mocks["environ"].update(
            {
                "JUJU_CHARM_HTTP_PROXY": TEST_PROXY_URL,
                "JUJU_CHARM_HTTPS_PROXY": TEST_PROXY_URL,
                "JUJU_CHARM_NO_PROXY": TEST_NO_PROXY,
            }
        )

        self.harness.charm._setup_proxy_env()
        self.assertEqual(self.harness.charm.proxy_env["http_proxy"], TEST_PROXY_URL)
        self.assertEqual(self.harness.charm.proxy_env["https_proxy"], TEST_PROXY_URL)
        self.assertEqual(self.harness.charm.proxy_env["no_proxy"], TEST_NO_PROXY)

    def test_setup_ssl_config(self):
        self.harness.update_config(
            {
                "override-ssl-cert-file": "/etc/ssl/certs/ca-certificates.crt",
            }
        )

        self.harness.charm._setup_ssl_env()
        self.assertEqual(
            self.harness.charm.ssl_env["SSL_CERT_FILE"], "/etc/ssl/certs/ca-certificates.crt"
        )

    def _add_ua_proxy_setup_calls(self, call_list, append=True):
        """Helper to generate the calls used for UA proxy setup."""
        proxy_calls = []
        if self.proxy_env["http_proxy"]:
            proxy_calls.append(
                call(
                    [
                        "ubuntu-advantage",
                        "config",
                        "set",
                        "http_proxy={}".format(self.proxy_env["http_proxy"]),
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

        if self.proxy_env["https_proxy"]:
            proxy_calls.append(
                call(
                    [
                        "ubuntu-advantage",
                        "config",
                        "set",
                        "https_proxy={}".format(self.proxy_env["https_proxy"]),
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


@pytest.fixture
def harness():
    """Glue code.

    This is helpful to slowly integrate pytest fixtures and `Context` while
    accommodating existing tests that use unittest.TestCase and `harness`.
    """
    harness = Harness(UbuntuAdvantageCharm)
    harness.begin()

    yield harness

    harness.cleanup()


@pytest.fixture
def mocks():
    """Glue code.

    This is helpful to slowly integrate pytest fixtures and `Context` while
    accommodating existing tests that use unittest.TestCase and `harness`. This
    fixture is generally required to avoid errors that derive from calling
    commands that need a "real" environment like subprocess calls.
    """
    mocks = {
        "call": patch("subprocess.call").start(),
        "check_call": patch("subprocess.check_call").start(),
        "run": patch("subprocess.run").start(),
        "apt": patch("charm.apt").start(),
        "status_output": patch("charm.get_status_output").start(),
        "install_livepatch": patch("charm.install_livepatch").start(),
        "disable_livepatch": patch("charm.disable_canonical_livepatch").start(),
    }

    yield mocks

    patch.stopall()


class TestOnConfigChanged:
    """pytest-based tests for the `on.config_changed` hook.

    Eventually these should use `Context` instead of `harness`.
    """

    def test_file_based_configs(self, harness, mocks, mock_uaclient_config):
        """Juju configs that set options in the Ubuntu Pro config file are correct."""
        with open(mock_uaclient_config) as f:
            actual_existing = yaml.safe_load(f)

        expected_existing = {
            "data_dir": "/var/lib/ubuntu-advantage",
            "log_level": "debug",
            "log_file": "/var/log/ubuntu-advantage.log",
            "contract_url": "https://contracts.canonical.com",
        }

        assert expected_existing == actual_existing

        harness.update_config(
            {
                "contract_url": "https://offline.contracts.canonical.com",
                "security_url": "https://offline.ubuntu.com/security",
            }
        )

        expected = {
            "contract_url": "https://offline.contracts.canonical.com",
            "data_dir": "/var/lib/ubuntu-advantage",
            "log_level": "debug",
            "log_file": "/var/log/ubuntu-advantage.log",
            "security_url": "https://offline.ubuntu.com/security",
        }

        with open(mock_uaclient_config) as f:
            actual = yaml.safe_load(f)

        assert expected == actual

    def test_security_url_unset(self, harness, mocks, mock_uaclient_config):
        """If the security_url is unset, it is removed from the config file."""
        harness.update_config({"security_url": "https://offline.ubuntu.com/security"})
        with open(mock_uaclient_config) as f:
            assert "security_url" in yaml.safe_load(f)

        harness.update_config({"security_url": ""})

        with open(mock_uaclient_config) as f:
            assert "security_url" not in yaml.safe_load(f)

    def test_apt_news_url_set(self, harness, mocks, mock_uaclient_config):
        """If apt_news_url is set, it is written under ua_config in the config file."""
        harness.update_config({"apt_news_url": "https://example.com/apt-news"})

        with open(mock_uaclient_config) as f:
            config = yaml.safe_load(f)

        assert config["ua_config"]["apt_news_url"] == "https://example.com/apt-news"

    def test_apt_news_url_unset(self, harness, mocks, mock_uaclient_config):
        """If apt_news_url is unset, it is removed from ua_config."""
        harness.update_config({"apt_news_url": "https://example.com/apt-news"})
        with open(mock_uaclient_config) as f:
            assert "apt_news_url" in yaml.safe_load(f).get("ua_config", {})

        harness.update_config({"apt_news_url": ""})

        with open(mock_uaclient_config) as f:
            config = yaml.safe_load(f)
            assert "apt_news_url" not in config.get("ua_config", {})

    def test_vulnerability_data_url_prefix_set(self, harness, mocks, mock_uaclient_config):
        """If vulnerability_data_url_prefix is set, it is written under ua_config."""
        harness.update_config(
            {"vulnerability_data_url_prefix": "https://example.com/cve-data"}
        )

        with open(mock_uaclient_config) as f:
            config = yaml.safe_load(f)

        assert config["ua_config"]["vulnerability_data_url_prefix"] == (
            "https://example.com/cve-data"
        )

    def test_vulnerability_data_url_prefix_unset(self, harness, mocks, mock_uaclient_config):
        """If vulnerability_data_url_prefix is unset, it is removed from ua_config."""
        harness.update_config(
            {"vulnerability_data_url_prefix": "https://example.com/cve-data"}
        )
        with open(mock_uaclient_config) as f:
            assert "vulnerability_data_url_prefix" in yaml.safe_load(f).get("ua_config", {})

        harness.update_config({"vulnerability_data_url_prefix": ""})

        with open(mock_uaclient_config) as f:
            config = yaml.safe_load(f)
            assert "vulnerability_data_url_prefix" not in config.get("ua_config", {})

    def test_nested_keys_and_flat_keys_coexist(self, harness, mocks, mock_uaclient_config):
        """Both nested and flat keys can coexist without overwriting each other."""
        # 1. Grab the current value from the harness before we change anything
        expected_contract_url = harness.charm.config.get("contract_url")

        harness.update_config(
            {
                "security_url": "https://offline-security.example.com",
                "apt_news_url": "https://example.com/apt-news",
                "vulnerability_data_url_prefix": "https://example.com/cve",
            }
        )

        with open(mock_uaclient_config) as f:
            config = yaml.safe_load(f)

        # Verify flat keys
        assert config["security_url"] == "https://offline-security.example.com"
        # Verify the specific value of the flat key we didn't touch matches the current config
        assert config["contract_url"] == expected_contract_url
        
        # Verify nested keys
        assert config["ua_config"]["apt_news_url"] == "https://example.com/apt-news"
        assert config["ua_config"]["vulnerability_data_url_prefix"] == "https://example.com/cve"

    def test_ua_config_parent_removed_when_empty(self, harness, mocks, mock_uaclient_config):
        """If all nested keys are removed, the ua_config parent key is also removed."""
        harness.update_config({
            "apt_news_url": "https://news",
            "vulnerability_data_url_prefix": "https://vuln"
        })
        
        # Remove both
        harness.update_config({
            "apt_news_url": "",
            "vulnerability_data_url_prefix": ""
        })

        with open(mock_uaclient_config) as f:
            config = yaml.safe_load(f)
            assert "ua_config" not in config


@pytest.fixture
def mock_uaclient_config():
    """Mock the uaclient.conf file for testing update_configuration."""
    initial_config = yaml.safe_load(DEFAULT_CLIENT_CONFIG)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
        yaml.dump(initial_config, f)
        temp_path = f.name

    with patch("charm.open", lambda path, mode: open(temp_path, mode)):
        yield temp_path

    Path(temp_path).unlink(missing_ok=True)


class TestUpdateConfiguration:
    """Test the update_configuration helper function."""

    def test_update_configuration_single_value(self, mock_uaclient_config):
        """Test updating a single configuration value."""
        update_configuration({"contract_url": "https://contracts.staging.canonical.com"})

        with open(mock_uaclient_config) as f:
            config = yaml.safe_load(f)

        assert config["contract_url"] == "https://contracts.staging.canonical.com"
        assert config["data_dir"] == "/var/lib/ubuntu-advantage"
        assert config["log_level"] == "debug"
        assert "ua_config" not in config

    def test_update_configuration_multiple_values(self, mock_uaclient_config):
        """Test updating multiple configuration values at once."""
        update_configuration(
            {
                "contract_url": "https://contracts.staging.canonical.com",
                "security_url": "https://offline.ubuntu.com/security",
            }
        )

        with open(mock_uaclient_config) as f:
            config = yaml.safe_load(f)

        assert config["contract_url"] == "https://contracts.staging.canonical.com"
        assert config["security_url"] == "https://offline.ubuntu.com/security"
        assert config["data_dir"] == "/var/lib/ubuntu-advantage"
        assert config["log_level"] == "debug"
        assert "ua_config" not in config

    def test_update_configuration_adds_new_key(self, mock_uaclient_config):
        """Test that new keys are added to the configuration."""
        update_configuration({"new_key": "new_value"})

        with open(mock_uaclient_config) as f:
            config = yaml.safe_load(f)

        assert config["new_key"] == "new_value"
        assert config["contract_url"] == "https://contracts.canonical.com"
        assert config["data_dir"] == "/var/lib/ubuntu-advantage"
        assert "ua_config" not in config

    def test_update_configuration_overwrites_existing_key(self, mock_uaclient_config):
        """Test that existing keys are properly overwritten."""
        existing_url = "https://ubuntu.com/security"
        new_url = "https://offline.ubuntu.com/security"

        with open(mock_uaclient_config, "r+") as f:
            config = yaml.safe_load(f)
            config["security_url"] = existing_url
            f.seek(0)
            yaml.dump(config, f)
            f.truncate()

        update_configuration({"security_url": new_url})

        with open(mock_uaclient_config) as f:
            content = f.read()
            config = yaml.safe_load(content)

        assert config["security_url"] == new_url
        assert existing_url not in content
        assert "ua_config" not in config
        
    def test_update_configuration_empty_dict(self, mock_uaclient_config):
        """Test that passing an empty dict doesn't break anything."""
        update_configuration({})

        with open(mock_uaclient_config) as f:
            config = yaml.safe_load(f)

        assert config["contract_url"] == "https://contracts.canonical.com"
        assert config["data_dir"] == "/var/lib/ubuntu-advantage"

    def test_update_configuration_nested_keys(self, mock_uaclient_config):
            """Test that specific keys are correctly nested under ua_config."""
            updates = {
                "apt_news_url": "https://news.local",
                "vulnerability_data_url_prefix": "https://vuln.local",
                "contract_url": "https://contracts.local"  # A flat key for comparison
            }
            
            update_configuration(updates)

            with open(mock_uaclient_config) as f:
                config = yaml.safe_load(f)

            # Check nesting
            assert config["ua_config"]["apt_news_url"] == "https://news.local"
            assert config["ua_config"]["vulnerability_data_url_prefix"] == "https://vuln.local"
            
            # Check that flat keys stayed flat
            assert config["contract_url"] == "https://contracts.local"

    def test_update_configuration_empty_ua_config_cleanup(self, mock_uaclient_config):
        """Test that update_configuration doesn't leave an empty ua_config block."""
        # Update only a flat key
        update_configuration({"contract_url": "https://new.contracts"})

        with open(mock_uaclient_config) as f:
            config = yaml.safe_load(f)

        assert "ua_config" not in config

    def test_update_configuration_nested_preserves_existing_siblings(self, mock_uaclient_config):
        """Test that updating one nested key doesn't remove others."""
        # First update apt_news_url
        update_configuration({"apt_news_url": "https://example.com/apt-news"})

        with open(mock_uaclient_config) as f:
            config = yaml.safe_load(f)
        assert config["ua_config"]["apt_news_url"] == "https://example.com/apt-news"

        # Now update vulnerability_data_url_prefix
        update_configuration(
            {"vulnerability_data_url_prefix": "https://example.com/cve-data"}
        )

        with open(mock_uaclient_config) as f:
            config = yaml.safe_load(f)

        assert config["ua_config"]["apt_news_url"] == "https://example.com/apt-news"
        assert config["ua_config"]["vulnerability_data_url_prefix"] == (
            "https://example.com/cve-data"
        )


class TestRemoveConfiguration:
    """Test the remove_configuration helper function."""

    def test_remove_configuration_single_key(self, mock_uaclient_config):
        """Test removing a single configuration key."""
        # First add a key
        update_configuration({"security_url": "https://offline.ubuntu.com/security"})

        with open(mock_uaclient_config) as f:
            config = yaml.safe_load(f)
        assert "security_url" in config

        # Now remove it
        remove_configuration(["security_url"])

        with open(mock_uaclient_config) as f:
            config = yaml.safe_load(f)

        assert "security_url" not in config
        assert config["contract_url"] == "https://contracts.canonical.com"
        assert config["data_dir"] == "/var/lib/ubuntu-advantage"

    def test_remove_configuration_multiple_keys(self, mock_uaclient_config):
        """Test removing multiple configuration keys at once."""
        # First add keys
        update_configuration(
            {"security_url": "https://offline.ubuntu.com/security", "custom_key": "custom_value"}
        )

        # Now remove them
        remove_configuration(["security_url", "custom_key"])

        with open(mock_uaclient_config) as f:
            config = yaml.safe_load(f)

        assert "security_url" not in config
        assert "custom_key" not in config
        assert config["contract_url"] == "https://contracts.canonical.com"

    def test_remove_configuration_nonexistent_key(self, mock_uaclient_config):
        """Test that removing a nonexistent key doesn't break anything."""
        remove_configuration(["nonexistent_key"])

        with open(mock_uaclient_config) as f:
            config = yaml.safe_load(f)

        assert config["contract_url"] == "https://contracts.canonical.com"
        assert config["data_dir"] == "/var/lib/ubuntu-advantage"

    def test_remove_configuration_empty_list(self, mock_uaclient_config):
        """Test that passing an empty list doesn't break anything."""
        remove_configuration([])

        with open(mock_uaclient_config) as f:
            config = yaml.safe_load(f)

        assert config["contract_url"] == "https://contracts.canonical.com"
        assert config["data_dir"] == "/var/lib/ubuntu-advantage"

    def test_remove_configuration_mixed_keys(self, mock_uaclient_config):
        """Test removing a mix of flat and nested keys at once."""
        update_configuration({
            "contract_url": "https://contracts.local",
            "apt_news_url": "https://news.local"
        })

        remove_configuration(["contract_url", "apt_news_url"])

        with open(mock_uaclient_config) as f:
            config = yaml.safe_load(f)

        assert "contract_url" not in config
        assert "ua_config" not in config

    def test_remove_configuration_nested_preserves_siblings(self, mock_uaclient_config):
        """Test that removing one nested key preserves others."""
        # Add both keys
        update_configuration(
            {
                "apt_news_url": "https://example.com/apt-news",
                "vulnerability_data_url_prefix": "https://example.com/cve",
            }
        )

        # Remove only apt_news_url
        remove_configuration(["apt_news_url"])

        with open(mock_uaclient_config) as f:
            config = yaml.safe_load(f)

        assert "apt_news_url" not in config.get("ua_config", {})
        assert config["ua_config"]["vulnerability_data_url_prefix"] == "https://example.com/cve"

    def test_remove_configuration_nested_cleans_up_parent(self, mock_uaclient_config):
        """Test that removing all nested keys removes ua_config entirely."""
        # Add both nested keys
        update_configuration(
            {
                "apt_news_url": "https://example.com/apt-news",
                "vulnerability_data_url_prefix": "https://example.com/cve",
            }
        )

        # Remove both
        remove_configuration(["apt_news_url", "vulnerability_data_url_prefix"])

        with open(mock_uaclient_config) as f:
            config = yaml.safe_load(f)

        # ua_config should be completely removed if empty
        assert "ua_config" not in config
        assert config["contract_url"] == "https://contracts.canonical.com"
