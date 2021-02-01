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


def parse_status():
    """Determine the enabled set of ubuntu-advantage services"""
    output = subprocess.check_output(["ubuntu-advantage", "status", "--all", "--format", "json"])
    if isinstance(output, bytes):
        output = output.decode("utf-8")
    return json.loads(output)


class UbuntuAdvantageCharm(CharmBase):
    """Charm to handle ubuntu-advantage installation and configuration"""
    _state = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        self._state.set_default(ppa=None, hashed_token=None)
        self.framework.observe(self.on.config_changed, self.config_changed)

    def config_changed(self, event):
        """Install and configure ubuntu-advantage tools and attachment"""
        logger.info("Beginning config_changed")
        ppa = self.config.get("ppa")
        if not ppa:
            self.unit.status = BlockedStatus("No ppa configured")
            return
        old_ppa = self._state.ppa
        if old_ppa != ppa:
            logger.info("Configuring ppa: %s", ppa)
            subprocess.check_call(["add-apt-repository", "--yes", ppa])
            subprocess.check_call(["apt", "update"])
            logger.info("Installing ubuntu-advantage-tools")
            subprocess.check_call(["apt", "install", "--yes", "--quiet", "ubuntu-advantage-tools"])
            self._state.ppa = ppa
            logger.info("Installed ubuntu-advantage-tools")
        token = self.config.get("token")
        if not token:
            self.unit.status = BlockedStatus("No token configured")
            return
        hashed_token = hashlib.sha256(token.encode("utf-8")).hexdigest()
        old_hashed_token = self._state.hashed_token
        status = parse_status()
        if status["attached"] and old_hashed_token != hashed_token:
            logger.info("Detaching ubuntu-advantage subscription in preparation for reattachment")
            subprocess.check_call(["ubuntu-advantage", "detach", "--assume-yes"])
            status = parse_status()
        if not status["attached"]:
            return_code = subprocess.call(["ubuntu-advantage", "attach", token])
            if return_code != 0:
                self.unit.status = BlockedStatus("Error attaching, possibly an invalid token?")
                return
            self._state.hashed_token = hashed_token
            status = parse_status()
        services = []
        for service in status["services"]:
            if service["status"] == "enabled":
                services.append(service["name"])
        message = "attached (" + ",".join(services) + ")"
        self.unit.status = ActiveStatus(message)
        logger.info("Finished config_changed")


if __name__ == "__main__":  # pragma: nocover
    main(UbuntuAdvantageCharm)
