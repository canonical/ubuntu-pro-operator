#!/usr/bin/env python3

# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import hashlib
import json
import logging
import subprocess

from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus


logger = logging.getLogger(__name__)


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


def get_status_output():
    """Return the parsed output from ubuntu-advantage status"""
    output = subprocess.check_output(["ubuntu-advantage", "status", "--all", "--format", "json"],
                                     encoding="utf-8")
    return json.loads(output)


class UbuntuAdvantageCharm(CharmBase):
    """Charm to handle ubuntu-advantage installation and configuration"""
    _state = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        self._state.set_default(hashed_token=None, package_needs_installing=True, ppa=None)
        self.framework.observe(self.on.config_changed, self.config_changed)

    def config_changed(self, event):
        """Install and configure ubuntu-advantage tools and attachment"""
        logger.info("Beginning config_changed")
        self._handle_ppa_state()
        self._handle_package_state()
        blocked = self._handle_token_state()
        if blocked:
            return
        self._handle_status_state()
        logger.info("Finished config_changed")

    def _handle_ppa_state(self):
        """Handle installing/removing ppa based on configuration and state"""
        ppa = self.config.get("ppa")
        old_ppa = self._state.ppa
        if old_ppa and old_ppa != ppa:
            logger.info("Removing previously installed ppa (%s)", old_ppa)
            remove_ppa(old_ppa)
        if ppa and ppa != old_ppa:
            logger.info("Installing ppa: %s", ppa)
            install_ppa(ppa)
            self._state.ppa = ppa
            # If ppa is changed, want to force an install of the package for potential updates
            self._state.package_needs_installing = True

    def _handle_package_state(self):
        """Install apt package if necessary"""
        if self._state.package_needs_installing:
            logger.info("Installing package ubuntu-advantage-tools")
            install_package("ubuntu-advantage-tools")
            self._state.package_needs_installing = False

    def _handle_token_state(self):
        """Handle subscription attachment and status output based on configuration and state"""
        token = self.config.get("token")
        old_hashed_token = self._state.hashed_token
        if not token:
            if old_hashed_token:
                logger.info("Detaching ubuntu-advantage subscription")
                subprocess.check_call(["ubuntu-advantage", "detach", "--assume-yes"])
                self._state.hashed_token = None
            self.unit.status = BlockedStatus("No token configured")
            return True
        hashed_token = hashlib.sha256(token.encode("utf-8")).hexdigest()
        status = get_status_output()
        if status["attached"] and hashed_token != old_hashed_token:
            logger.info("Detaching ubuntu-advantage subscription in preparation for reattachment")
            subprocess.check_call(["ubuntu-advantage", "detach", "--assume-yes"])
            self._state.hashed_token = None
            status = get_status_output()
        if not status["attached"]:
            return_code = subprocess.call(["ubuntu-advantage", "attach", token])
            if return_code != 0:
                self.unit.status = BlockedStatus("Error attaching, possibly an invalid token?")
                return True
            self._state.hashed_token = hashed_token

    def _handle_status_state(self):
        """Parse status output to determine which services are active"""
        status = get_status_output()
        services = []
        for service in status.get("services"):
            if service.get("status") == "enabled":
                services.append(service.get("name"))
        message = "attached (" + ",".join(services) + ")"
        self.unit.status = ActiveStatus(message)


if __name__ == "__main__":  # pragma: nocover
    main(UbuntuAdvantageCharm)
