#!/usr/bin/env python3

# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import hashlib
import json
import logging
import subprocess
import yaml

from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus


logger = logging.getLogger(__name__)

UACLIENT_CONFIG = '/etc/ubuntu-advantage/uaclient.conf'
DEFAULT_CONTRACT_URL = 'https://contracts.canonical.com'


def install_ppa(ppa):
    """Install specified ppa"""
    subprocess.check_call(["add-apt-repository", "--yes", ppa])


def remove_ppa(ppa):
    """Remove specified ppa"""
    subprocess.check_call(["add-apt-repository", "--remove", "--yes", ppa])


def install_package(package):
    """Install specified apt package (after performing an apt update)"""
    subprocess.check_call(["apt", "update"])
    subprocess.check_call(["apt", "install", "--yes", "--quiet", package])


def remove_package(package):
    """Remove specified apt package"""
    subprocess.check_call(["apt", "remove", "--yes", "--quiet", package])


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
        self._state.set_default(
            contract_url=None,
            hashed_token=None,
            package_needs_installing=True,
            ppa=None)
        self.framework.observe(self.on.config_changed, self.config_changed)

    def config_changed(self, event):
        """Install and configure ubuntu-advantage tools and attachment"""
        logger.info("Beginning config_changed")
        self.unit.status = MaintenanceStatus("Configuring")
        self._handle_ppa_state()
        self._handle_package_state()
        self._handle_token_state()
        if isinstance(self.unit.status, BlockedStatus):
            return
        self._handle_status_state()
        logger.info("Finished config_changed")

    def _detach(self):
        logger.info("Detaching ubuntu-advantage subscription")
        subprocess.check_call(["ubuntu-advantage", "detach", "--assume-yes"])

    def _attach(self, token):
        return_code = subprocess.call(["ubuntu-advantage", "attach", token])
        if return_code != 0:
            self.unit.status = BlockedStatus("Error attaching, possibly an invalid token?")
            return

    def _handle_ppa_state(self):
        """Handle installing/removing ppa based on configuration and state"""
        ppa = self.config.get("ppa", "").strip()
        old_ppa = self._state.ppa
        if old_ppa and old_ppa != ppa:
            logger.info("Removing previously installed ppa (%s)", old_ppa)
            remove_ppa(old_ppa)
            self._state.ppa = None
            # If ppa is changed, want to remove the previous version of the package for consistency
            self._state.package_needs_installing = True
        if ppa and ppa != old_ppa:
            logger.info("Installing ppa: %s", ppa)
            install_ppa(ppa)
            self._state.ppa = ppa
            # If ppa is changed, want to force an install of the package for potential updates
            self._state.package_needs_installing = True

    def _handle_package_state(self):
        """Install apt package if necessary"""
        if self._state.package_needs_installing:
            logger.info("Removing package ubuntu-advantage-tools")
            remove_package("ubuntu-advantage-tools")
            logger.info("Installing package ubuntu-advantage-tools")
            install_package("ubuntu-advantage-tools")
            self._state.package_needs_installing = False

    def _handle_token_state(self):
        """Handle subscription attachment and status output based on configuration and state"""
        token = self.config.get("token", "").strip()
        hashed_token = hashlib.sha256(token.encode("utf-8")).hexdigest()
        old_hashed_token = self._state.hashed_token or ''
        contract_url = self.config.get("contract_url", "").strip()
        old_contract_url = self._state.contract_url or ''

        config_changed = contract_url != old_contract_url
        token_changed = (token or old_hashed_token) and hashed_token != old_hashed_token

        if not config_changed and not token_changed:
            if not token:
                self.unit.status = BlockedStatus("No token configured")
                return
            return

        status = get_status_output()

        if config_changed or token_changed:
            # Detach if either the config (contract_url) or the token have changed.
            if status["attached"]:
                self._detach()
                self._state.hashed_token = None

        if config_changed:
            self._update_uaclient_config(contract_url)

        if not token:
            self.unit.status = BlockedStatus("No token configured")
            return

        if token:
            self._attach(token)
            self._state.hashed_token = hashed_token

    def _update_uaclient_config(self, contract_url):
        with open(UACLIENT_CONFIG, 'r') as f:
            client_config = yaml.safe_load(f)

        if not contract_url:
            # Contract url is not set in charm config - revert to original one.
            contract_url = DEFAULT_CONTRACT_URL

        client_config['contract_url'] = contract_url
        with open(UACLIENT_CONFIG, 'w') as f:
            yaml.dump(client_config, f)
        self._state.contract_url = contract_url

    def _handle_status_state(self):
        """Parse status output to determine which services are active"""
        status = get_status_output()
        services = []
        for service in status.get("services"):
            if service.get("status") == "enabled":
                services.append(service.get("name"))
        message = "Attached (" + ",".join(services) + ")"
        self.unit.status = ActiveStatus(message)


if __name__ == "__main__":  # pragma: nocover
    main(UbuntuAdvantageCharm)
