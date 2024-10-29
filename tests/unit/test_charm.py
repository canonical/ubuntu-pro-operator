# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import json
from subprocess import CalledProcessError
from textwrap import dedent
from unittest import TestCase
from unittest.mock import call, mock_open, patch

from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus
from ops.testing import Harness

from charm import UbuntuAdvantageCharm
from exceptions import APIError

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
            "open": patch("builtins.open").start(),
            "environ": patch.dict("os.environ", clear=True).start(),
            "apt": patch("charm.apt").start(),
            "install_livepatch": patch("charm.install_livepatch").start(),
            "disable_livepatch": patch("charm.disable_canonical_livepatch").start(),
            "attach_status": patch("charm.attach_status").start(),
            "detach_sub": patch("charm.detach_sub").start(),
            "enable_service": patch("charm.enable_service").start(),
            "get_enabled_services": patch("charm.get_enabled_services").start(),
        }
        self.mocks["call"].return_value = 0
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

    def test_config_changed_ppa_new(self):
        self.harness.update_config({"ppa": "ppa:ua-client/stable"})
        self.assertEqual(self.mocks["check_call"].call_count, 3)
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
        self.assertEqual(self.mocks["check_call"].call_count, 3)
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
        self.assertEqual(self.mocks["check_call"].call_count, 3)
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
        self.assertEqual(self.mocks["check_call"].call_count, 3)
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

    @patch("charm.attach_sub", side_effect=[{"enabled": [], "reboot_required": False}])
    @patch("charm.get_enabled_services", return_value=[])
    def test_config_changed_token_unattached(self, m_enabled_services, m_attach_sub):
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
        assert m_attach_sub.call_count == 1
        self.assertEqual(
            self.harness.charm._state.hashed_token,
            "4c5dc9b7708905f77f5e5d16316b5dfb425e68cb326dcd55a860e90a7707031e",
        )
        self.assertEqual(self.harness.model.unit.status, ActiveStatus("Attached ()"))

    @patch(
        "charm.attach_sub",
        side_effect=[
            {"enabled": [], "reboot_required": False},
            {"enabled": [], "reboot_required": False},
        ],
    )
    @patch("charm.get_enabled_services", return_value=[])
    @patch("charm.attach_status", side_effect=[False, True])
    def test_config_changed_token_reattach(
        self, m_attach_status, m_enabled_services, m_attach_sub
    ):
        self.harness.update_config({"token": "test-token"})
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
        assert m_attach_status.call_count == 1
        assert m_attach_sub.call_count == 1
        assert m_enabled_services.call_count == 1
        self.assertEqual(
            self.harness.charm._state.hashed_token,
            "4c5dc9b7708905f77f5e5d16316b5dfb425e68cb326dcd55a860e90a7707031e",
        )

        self.mocks["check_call"].reset_mock()
        self.harness.update_config({"token": "test-token-2"})
        self.assertEqual(self.mocks["check_call"].call_count, 2)

        assert m_attach_status.call_count == 2
        assert m_attach_sub.call_count == 2
        assert m_enabled_services.call_count == 2
        self.assertEqual(
            self.harness.charm._state.hashed_token,
            "ab8a83efb364bf3f6739348519b53c8e8e0f7b4c06b6eeb881ad73dcf0059107",
        )
        self.assertEqual(self.harness.model.unit.status, ActiveStatus("Attached ()"))

    @patch(
        "charm.attach_status",
        side_effect=[
            False,
            True,
        ],
    )
    @patch(
        "pro_client.full_token_attach",
        side_effect=[
            {"errors": [{"code": "attach-invalid-token", "title": "Invalid token."}]},
            {"enabled_services": [], "reboot_required": False},
        ],
    )
    @patch("charm.get_enabled_services", return_value=[])
    def test_attach_retry_on_failure(
        self, m_enabled_services, m_full_token_attach, m_attach_status
    ):
        # Retries once and then passes
        # Only simulating if any errors are raised, a retry mechanism is called
        # and if one retry passes, we are attached
        from pro_client import FullTokenAttachOptions

        self.harness.update_config({"token": "test-token"})
        m_full_token_attach.assert_has_calls(
            [
                call(FullTokenAttachOptions(token="test-token", auto_enable_services=True)),
            ]
        )
        assert m_full_token_attach.call_count == 2
        self.assertEqual(self.harness.model.unit.status, ActiveStatus("Attached ()"))

    @patch(
        "charm.attach_sub",
        side_effect=[APIError("attach-invalid-token", "Invalid token.")],
    )
    def test_config_changed_attach_failure(self, m_attach_subscription):
        self.harness.update_config({"token": "test-token"})
        assert m_attach_subscription.call_count == 1
        self.assertEqual(
            self.harness.model.unit.status,
            BlockedStatus("Error code: attach-invalid-token, message: Invalid token."),
        )

    @patch("charm.attach_sub", return_value=(0, ""))
    def test_attach_with_no_services(self, m_attach_sub):
        self.harness.update_config({"token": "test-token"})
        m_attach_sub.assert_called_once_with("test-token", None, auto_enable=True)

    @patch(
        "pro_client.full_token_attach",
        side_effect=[
            {"enabled_services": [], "reboot_required": False},
        ],
    )
    @patch("pro_client.enable_service")
    def test_attach_with_added_services(self, m_enable_service, m_full_token_attach):
        from pro_client import FullTokenAttachOptions

        self.harness.update_config({"token": "test-token", "services": "fips"})
        m_full_token_attach.assert_has_calls(
            [
                call(FullTokenAttachOptions(token="test-token", auto_enable_services=False)),
            ]
        )
        assert m_enable_service.call_count == 1
        m_enable_service.assert_called_once_with(service="fips")

    @patch(
        "charm.attach_status",
        side_effect=[False, True],
    )
    @patch("charm.attach_sub")
    @patch("charm.detach_sub")
    def test_config_changed_token_detach(self, m_detach_sub, m_attach_sub, m_get_status_output):
        self.harness.update_config({"token": "test-token"})
        self.assertEqual(
            self.harness.charm._state.hashed_token,
            "4c5dc9b7708905f77f5e5d16316b5dfb425e68cb326dcd55a860e90a7707031e",
        )

        self.mocks["check_call"].reset_mock()
        self.harness.update_config({"token": ""})

        assert m_detach_sub.call_count == 1
        assert m_attach_sub.call_count == 1
        self.assertIsNone(self.harness.charm._state.hashed_token)
        self.assertEqual(self.harness.model.unit.status, BlockedStatus("No token configured"))

    @patch("charm.attach_sub")
    @patch(
        "charm.attach_status",
        side_effect=[False, True],
    )
    def test_config_changed_token_update_after_block(self, m_attach_status, m_attach_sub):
        self.harness.update_config()
        self.assertIsInstance(self.harness.model.unit.status, BlockedStatus)

        self.harness.update_config({"token": "test-token"})
        assert m_attach_status.call_count == 2
        assert m_attach_sub.call_count == 1
        self.assertIsInstance(self.harness.model.unit.status, ActiveStatus)

    def test_config_changed_ppa_contains_newline(self):
        self.harness.update_config({"ppa": "ppa:ua-client/stable\n"})
        self.mocks["check_call"].assert_has_calls(
            [
                call(["add-apt-repository", "--yes", "ppa:ua-client/stable"], env=self.proxy_env),
            ]
        )
        self.assertEqual(self.harness.charm._state.ppa, "ppa:ua-client/stable")

    def test_config_changed_contract_url(self):
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

    @patch("charm.detach_sub")
    @patch(
        "charm.attach_sub",
        side_effect=[
            {"enabled_services": [], "reboot_required": False},
            {"enabled_services": [], "reboot_required": False},
        ],
    )
    @patch(
        "charm.attach_status",
        side_effect=[
            False,
            True,
            True,
        ],
    )
    def test_config_changed_contract_url_reattach(
        self, m_attach_status, m_attach_sub, m_detach_sub
    ):
        # TODO: Update
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
        assert m_detach_sub.call_count == 1
        self.assertEqual(self.harness.model.unit.status, ActiveStatus("Attached ()"))

        self.mocks["check_call"].reset_mock()
        self.mocks["open"].reset_mock()
        mock_open(self.mocks["open"], read_data=DEFAULT_CLIENT_CONFIG)
        self.harness.update_config()
        self.mocks["open"].assert_not_called()
        assert m_attach_status.call_count == 3
        assert m_attach_sub.call_count == 2

    @patch(
        "charm.attach_status",
        side_effect=[
            False,
            True,
        ],
    )
    def test_config_changed_unset_contract_url(self, m_attach_status):
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
        assert m_attach_status.call_count == 2
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

    # Commented out until we can figure out if we can set certification files
    # for the pro client api
    #
    # def test_config_changed_set_ssl_cert_file_override(self):
    #     # Set proxy override once.
    #     self.harness.update_config(
    #         {
    #             "override-ssl-cert-file": "/etc/ssl/certs/ca-certificates.crt",
    #         }
    #     )
    #     self.mocks["run"].reset_mock()
    #     self.harness.update_config(
    #         {
    #             "token": "token",
    #         }
    #     )
    #     self.mocks["run"].assert_has_calls(
    #         [
    #             call(
    #                 ["ubuntu-advantage", "attach", "token"],
    #                 stdout=PIPE,
    #                 stderr=PIPE,
    #                 env={"SSL_CERT_FILE": "/etc/ssl/certs/ca-certificates.crt"},
    #             ),
    #         ]
    #     )
    #     self.mocks["run"].reset_mock()

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
    @patch("charm.attach_status", return_value=True)
    @patch("charm.enable_service")
    def test_canonical_livepatch_unset_server_livepatch_enabled(
        self,
        m_enable_service,
        m_attach_status,
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
        self.assertEqual(m_enable_service.call_count, 1)
        m_enable_service.assert_called_once_with("livepatch")

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
