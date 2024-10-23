#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charmed Operator to enable Ubuntu Pro (https://ubuntu.com/pro) subscriptions."""

import hashlib
import json
import logging
import os
import subprocess
from contextlib import contextmanager
from tempfile import NamedTemporaryFile

import yaml
from charms.operator_libs_linux.v0 import apt
from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus

from exceptions import ProcessExecutionError
from livepatch import (
    disable_canonical_livepatch,
    enable_livepatch_server,
    install_livepatch,
    set_livepatch_server,
)
from pro_client import (
    attach_status,
    attach_sub,
    detach_sub,
    enable_service,
    get_enabled_services,
)
from utils import parse_services, retry, update_configuration

logger = logging.getLogger(__name__)

DEFAULT_LIVEPATCH_SERVER = "https://livepatch.canonical.com"


def install_ppa(ppa, env):
    """Install specified ppa."""
    subprocess.check_call(["add-apt-repository", "--yes", ppa], env=env)


def remove_ppa(ppa, env):
    """Remove specified ppa."""
    subprocess.check_call(["add-apt-repository", "--remove", "--yes", ppa], env=env)


class UbuntuAdvantageCharm(CharmBase):
    """Charm to handle ubuntu-advantage installation and configuration."""

    _state = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        self._setup_proxy_env()
        self._setup_ssl_env()
        self._state.set_default(
            contract_url=None,
            hashed_token=None,
            package_needs_installing=True,
            ppa=None,
            livepatch_installed=False,
            hashed_livepatch_token=None,
        )

        self.framework.observe(self.on.config_changed, self.config_changed)

    def _setup_proxy_env(self):
        """Setup proxy variables from model."""
        self.proxy_env = dict(os.environ)
        self.proxy_env["http_proxy"] = self.config.get(
            "override-http-proxy"
        ) or self.proxy_env.get("JUJU_CHARM_HTTP_PROXY", "")
        self.proxy_env["https_proxy"] = self.config.get(
            "override-https-proxy"
        ) or self.proxy_env.get("JUJU_CHARM_HTTPS_PROXY", "")
        self.proxy_env["no_proxy"] = self.proxy_env.get("JUJU_CHARM_NO_PROXY", "")

        # The values for 'http_proxy' and 'https_proxy' will be used for the
        # PPA install/remove operations (passed as environment variables), as
        # well as for configuring the UA client.
        # The value for 'no_proxy' is only used by the PPA install/remove
        # operations (passed as an environment variable).

        # log proxy environment variables for debugging
        for envvar, value in self.proxy_env.items():
            if envvar.endswith("proxy".lower()):
                logger.debug("Envvar '%s' => '%s'", envvar, value)

    def _setup_ssl_env(self):
        """Setup openssl variables from model."""
        self.ssl_env = dict(os.environ)
        value = self.config.get("override-ssl-cert-file", "")
        self.ssl_env["SSL_CERT_FILE"] = value
        logger.debug("Envvar 'SSL_CERT_FILE' => '%s'", value)

    def config_changed(self, event):
        """Install and configure ubuntu-advantage tools and attachment."""
        logger.info("Beginning config_changed")
        self.unit.status = MaintenanceStatus("Configuring")
        self._setup_proxy_env()
        self._setup_ssl_env()
        self._handle_ppa_state()
        self._handle_package_state()
        self._configure_livepatch()
        if isinstance(self.unit.status, BlockedStatus):
            return
        self._handle_subscription_state()
        if isinstance(self.unit.status, BlockedStatus):
            return
        self._handle_status_state()
        logger.info("Finished config_changed")

    def _handle_ppa_state(self):
        """Handle installing/removing ppa based on configuration and state."""
        ppa = self.config.get("ppa", "").strip()
        old_ppa = self._state.ppa

        if old_ppa and old_ppa != ppa:
            logger.info("Removing previously installed ppa (%s)", old_ppa)
            remove_ppa(old_ppa, self.proxy_env)
            self._state.ppa = None
            # If ppa is changed, want to remove the previous version of the package for consistency
            self._state.package_needs_installing = True

        if ppa and ppa != old_ppa:
            logger.info("Installing ppa: %s", ppa)
            install_ppa(ppa, self.proxy_env)
            self._state.ppa = ppa
            # If ppa is changed, want to force an install of the package for potential updates
            self._state.package_needs_installing = True

    def _handle_package_state(self):
        """Install apt package if necessary."""
        if self._state.package_needs_installing:
            logger.info("Installing package ubuntu-advantage-tools")
            apt.add_package("ubuntu-advantage-tools", update_cache=True)
            self._state.package_needs_installing = False

    def _configure_livepatch(self):
        """Configure the onprem livepatch server and token."""
        livepatch_server = self.config.get("livepatch_server_url", "").strip()
        livepatch_token = self.config.get("livepatch_token", "").strip()
        hashed_livepatch_token = hashlib.sha256(livepatch_token.encode()).hexdigest()

        try:
            if livepatch_server and livepatch_token:
                if hashed_livepatch_token != self._state.hashed_livepatch_token:
                    if not self._state.livepatch_installed:
                        install_livepatch()
                        self._state.livepatch_installed = True
                    set_livepatch_server(livepatch_server)
                    disable_canonical_livepatch()
                    enable_livepatch_server(livepatch_token)
                    self._state.hashed_livepatch_token = hashed_livepatch_token
            elif (
                self._state.livepatch_installed and self._state.hashed_livepatch_token is not None
            ):
                # Set to default server
                enabled_services = get_enabled_services()
                logger.info("Setting livepatch on-prem server to default")
                set_livepatch_server(DEFAULT_LIVEPATCH_SERVER)
                # Disabling canonical-livepatch when already disabled does not throw an error
                disable_canonical_livepatch()
                is_attached = attach_status()
                if is_attached and "livepatch" in enabled_services:
                    logger.info("Enabling livepatch hosted server using Pro client")
                    enable_service("livepatch")
                self._state.hashed_livepatch_token = None
        except ProcessExecutionError as e:
            logger.error("Failed to configure livepatch: %s", str(e))
            self.unit.status = BlockedStatus(str(e))

    def _handle_subscription_state(self):
        """Handle uaclient configuration and subscription attachment."""
        token = self.config.get("token", "").strip()
        hashed_token = hashlib.sha256(token.encode("utf-8")).hexdigest()
        old_hashed_token = self._state.hashed_token
        token_changed = hashed_token != old_hashed_token

        contract_url = self.config.get("contract_url", "").strip()
        old_contract_url = self._state.contract_url
        config_changed = contract_url != old_contract_url

        # Add the proxy configuration to the UA client.
        # This is needed for attach/detach/status commands used by the charm,
        # as well as regular tool operations.
        self._configure_ua_proxy()

        if config_changed:
            logger.info("Updating uaclient.conf")
            update_configuration(contract_url)
            self._state.contract_url = contract_url

        is_attached = attach_status()
        if is_attached and (config_changed or token_changed):
            detach_sub()
            self._state.hashed_token = None

        if not token:
            self.unit.status = BlockedStatus("No token configured")
            return
        elif config_changed or token_changed:
            logger.info("Attaching ubuntu-advantage subscription")
            try:
                enable_services = parse_services(self.config.get("services", "").strip())
                res = attach_sub(token, enable_services, auto_enable=True)
            except Exception as e:
                self.unit.status = BlockedStatus(str(e))
                return
            self._state.hashed_token = hashed_token

    def _handle_status_state(self):
        """Parse status output to determine which services are active."""
        services = get_enabled_services()
        message = "Attached (" + ",".join(services) + ")"
        self.unit.status = ActiveStatus(message)

    def _configure_ua_proxy(self):
        """Configure the proxy options for the ubuntu-advantage client."""
        for config_key in ("http_proxy", "https_proxy"):
            if self.proxy_env[config_key]:
                subprocess.check_call(
                    [
                        "ubuntu-advantage",
                        "config",
                        "set",
                        "{}={}".format(config_key, self.proxy_env[config_key]),
                    ]
                )
            else:
                subprocess.check_call(
                    [
                        "ubuntu-advantage",
                        "config",
                        "unset",
                        config_key,
                    ]
                )


if __name__ == "__main__":  # pragma: nocover
    main(UbuntuAdvantageCharm)
