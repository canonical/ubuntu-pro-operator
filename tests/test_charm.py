# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

from subprocess import CalledProcessError
from unittest import TestCase
from unittest.mock import patch, call

from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus
from ops.testing import Harness

from charm import UbuntuAdvantageCharm


class TestCharm(TestCase):
    def setUp(self):
        self.harness = Harness(UbuntuAdvantageCharm)
        self.addCleanup(self.harness.cleanup)

    @patch('subprocess.check_call')
    def test_install(self, _check_call):
        self.harness.begin()
        self.harness.charm.on.install.emit()
        self.assertEqual(_check_call.call_count, 3)
        _check_call.assert_has_calls([
            call(['add-apt-repository', '--yes', 'ppa:ua-client/stable']),
            call(['apt', 'update']),
            call(['apt', 'install', '--yes', '--quiet', 'ubuntu-advantage-tools'])
        ])
        self.assertIsInstance(self.harness.model.unit.status, ActiveStatus)

    @patch('subprocess.check_call')
    def test_install_fails(self, _check_call):
        _check_call.side_effect = CalledProcessError('apt failure', 'add-apt-repository')
        self.harness.begin()
        with self.assertRaises(CalledProcessError):
            self.harness.charm.on.install.emit()
        self.assertIsInstance(self.harness.model.unit.status, MaintenanceStatus)

    def test_config_changed_no_token(self):
        self.harness.begin()
        self.harness.charm.on.config_changed.emit()
        self.assertIsInstance(self.harness.model.unit.status, BlockedStatus)

    @patch('subprocess.check_output')
    def test_config_changed_already_attached(self, _check_output):
        _check_output.return_value = '{"attached":true}'
        self.harness.update_config({'ubuntu-advantage-token': 'test-token'})
        self.harness.begin()
        self.harness.charm.on.config_changed.emit()
        self.assertEqual(_check_output.call_count, 1)
        _check_output.assert_called_with(['ubuntu-advantage', 'status', '--format', 'json'])
        self.assertIsInstance(self.harness.model.unit.status, ActiveStatus)

    @patch('subprocess.check_call')
    @patch('subprocess.check_output')
    def test_config_changed_attach(self, _check_output, _check_call):
        _check_output.return_value = '{"attached":false}'
        self.harness.update_config({'ubuntu-advantage-token': 'test-token'})
        self.harness.begin()
        self.harness.charm.on.config_changed.emit()
        self.assertEqual(_check_output.call_count, 1)
        _check_output.assert_called_with(['ubuntu-advantage', 'status', '--format', 'json'])
        self.assertEqual(_check_call.call_count, 1)
        _check_call.assert_called_with(['ubuntu-advantage', 'attach', 'test-token'])
        self.assertIsInstance(self.harness.model.unit.status, ActiveStatus)
