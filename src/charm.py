#!/usr/bin/env python3

# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import hashlib
import json
import logging
import os
import subprocess
import yaml

from charms.operator_libs_linux.v0 import apt
from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus


logger = logging.getLogger(__name__)


def install_ppa(ppa, env):
    """Install specified ppa"""
    subprocess.check_call(["add-apt-repository", "--yes", ppa], env=env)


def remove_ppa(ppa, env):
    """Remove specified ppa"""
    subprocess.check_call(["add-apt-repository", "--remove", "--yes", ppa], env=env)


def update_configuration(contract_url):
    """Write the contract_url to the uaclient configuration file"""
    with open("/etc/ubuntu-advantage/uaclient.conf", "r+") as f:
        client_config = yaml.safe_load(f)
        client_config["contract_url"] = contract_url
        f.seek(0)
        yaml.dump(client_config, f)
        f.truncate()


def detach_subscription():
    """Detach from any ubuntu-advantage subscription"""
    subprocess.check_call(["ubuntu-advantage", "detach", "--assume-yes"])


def attach_subscription(token):
    """Attach an ubuntu-advantage subscription using the specified token"""
    return subprocess.call(["ubuntu-advantage", "attach", token])


def get_status_output():
    """Return the parsed output from ubuntu-advantage status"""
    output = subprocess.check_output(["ubuntu-advantage", "status", "--all", "--format", "json"])
    # handle different return type from xenial
    if isinstance(output, bytes):
        output = output.decode("utf-8")
    return json.loads(output)


class UbuntuAdvantageCharm(CharmBase):
    """Charm to handle ubuntu-advantage installation and configuration"""
    _state = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        self._setup_proxy_env()
        self._state.set_default(
            contract_url=None,
            hashed_token=None,
            package_needs_installing=True,
            ppa=None)

        self.framework.observe(self.on.config_changed, self.config_changed)

    def _setup_proxy_env(self):
        """Setup proxy variables from model"""
        self.env = dict(os.environ)
        self.env['http_proxy'] = self.env.get('JUJU_CHARM_HTTP_PROXY', '')
        self.env['https_proxy'] = self.env.get('JUJU_CHARM_HTTPS_PROXY', '')
        self.env['no_proxy'] = self.env.get('JUJU_CHARM_NO_PROXY', '')

        # The values for 'http_proxy' and 'https_proxy' will be used for the
        # PPA install/remove operations (passed as environment variables), as
        # well as for configuring the UA client.
        # The value for 'no_proxy' is only used by the PPA install/remove
        # operations (passed as an environment variable).

        # log proxy environment variables for debugging
        for envvar, value in self.env.items():
            if envvar.endswith("proxy".lower()):
                logger.debug("Envvar '%s' => '%s'", envvar, value)

    def config_changed(self, event):
        """Install and configure ubuntu-advantage tools and attachment"""
        logger.info("Beginning config_changed")
        self.unit.status = MaintenanceStatus("Configuring")
        self._handle_ppa_state()
        self._handle_package_state()
        self._handle_subscription_state()
        if isinstance(self.unit.status, BlockedStatus):
            return
        self._handle_status_state()
        logger.info("Finished config_changed")

    def _handle_ppa_state(self):
        """Handle installing/removing ppa based on configuration and state"""
        ppa = self.config.get("ppa", "").strip()
        old_ppa = self._state.ppa

        if old_ppa and old_ppa != ppa:
            logger.info("Removing previously installed ppa (%s)", old_ppa)
            remove_ppa(old_ppa, self.env)
            self._state.ppa = None
            # If ppa is changed, want to remove the previous version of the package for consistency
            self._state.package_needs_installing = True

        if ppa and ppa != old_ppa:
            logger.info("Installing ppa: %s", ppa)
            install_ppa(ppa, self.env)
            self._state.ppa = ppa
            # If ppa is changed, want to force an install of the package for potential updates
            self._state.package_needs_installing = True

    def _handle_package_state(self):
        """Install apt package if necessary"""
        if self._state.package_needs_installing:
            logger.info("Removing package ubuntu-advantage-tools")
            apt.remove_package("ubuntu-advantage-tools")
            logger.info("Installing package ubuntu-advantage-tools")
            apt.add_package("ubuntu-advantage-tools", update_cache=True)
            self._state.package_needs_installing = False

    def _handle_subscription_state(self):
        """Handle uaclient configuration and subscription attachment"""
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

        status = get_status_output()
        if status["attached"] and (config_changed or token_changed):
            logger.info("Detaching ubuntu-advantage subscription")
            detach_subscription()
            self._state.hashed_token = None

        if config_changed:
            logger.info("Updating uaclient.conf")
            update_configuration(contract_url)
            self._state.contract_url = contract_url

        if not token:
            self.unit.status = BlockedStatus("No token configured")
            return
        elif config_changed or token_changed:
            logger.info("Attaching ubuntu-advantage subscription")
            return_code = attach_subscription(token)
            if return_code != 0:
                message = "Error attaching, possibly an invalid token or contract_url?"
                self.unit.status = BlockedStatus(message)
                return
            self._state.hashed_token = hashed_token

    def _handle_status_state(self):
        """Parse status output to determine which services are active"""
        status = get_status_output()
        services = []
        for service in status.get("services"):
            if service.get("status") == "enabled":
                services.append(service.get("name"))
        message = "Attached (" + ",".join(services) + ")"
        self.unit.status = ActiveStatus(message)

    def _configure_ua_proxy(self):
        """Configure the proxy options for the ubuntu-advantage client"""
        for config_key in ("http_proxy", "https_proxy"):
            subprocess.check_call(
                [
                    "ubuntu-advantage",
                    "config",
                    "set",
                    "{}={}".format(config_key, self.env[config_key]),
                ]
            )


if __name__ == "__main__":  # pragma: nocover
    main(UbuntuAdvantageCharm)
