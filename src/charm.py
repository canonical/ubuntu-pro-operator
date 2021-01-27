#!/usr/bin/env python3

# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import logging
import shlex
import subprocess

from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus


logger = logging.getLogger(__name__)


class UbuntuAdvantageCharm(CharmBase):
    def __init__(self, *args):
        super().__init__(*args)
        self.framework.observe(self.on.install, self.install)
        self.framework.observe(self.on.config_changed, self.config_changed)

    def install(self, event):
        logger.info('Beginning install')
        subprocess.check_call(['add-apt-repository', '--yes', 'ppa:ua-client/stable'])
        subprocess.check_call(['apt', 'update'])
        subprocess.check_call(['apt', 'install', '--yes', '--quiet', 'ubuntu-advantage-tools'])
        self.unit.status = ActiveStatus('installed')
        logger.info('Finished install')

    def config_changed(self, event):
        logger.info('Beginning config_changed')
        token = self.config.get('ubuntu-advantage-token')
        if not token:
            self.unit.status = BlockedStatus('No token configured')
            return
        output = subprocess.check_output(['ubuntu-advantage', 'status', '--format', 'json'])
        status = json.loads(output)
        if not status['attached']:
            subprocess.check_call(['ubuntu-advantage', 'attach', shlex.quote(token)])
        self.unit.status = ActiveStatus('attached')
        logger.info('Finished config_changed')


if __name__ == "__main__":
    main(UbuntuAdvantageCharm)
