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
from utils.retry import retry

logger = logging.getLogger(__name__)


def install_ppa(ppa, env):
    """Install specified ppa."""
    subprocess.check_call(["add-apt-repository", "--yes", ppa], env=env)


def remove_ppa(ppa, env):
    """Remove specified ppa."""
    subprocess.check_call(["add-apt-repository", "--remove", "--yes", ppa], env=env)


def update_configuration(contract_url):
    """Write the contract_url to the uaclient configuration file."""
    with open("/etc/ubuntu-advantage/uaclient.conf", "r+") as f:
        client_config = yaml.safe_load(f)
        client_config["contract_url"] = contract_url
        f.seek(0)
        yaml.dump(client_config, f)
        f.truncate()


def detach_subscription():
    """Detach from any ubuntu-advantage subscription."""
    logger.info("Detaching ubuntu-advantage subscription")
    subprocess.check_call(["ubuntu-advantage", "detach", "--assume-yes"])


def set_livepatch_server(server):
    """Set the livepatch server."""
    logger.info("Setting livepatch on-prem server")
    result = subprocess.run(
        ["canonical-livepatch", "config", f"remote-server={server}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.error("Error setting canonical-livepatch server: %s", result.stderr)
        raise ProcessExecutionError(result.args, result.returncode, result.stdout, result.stderr)


def enable_livepatch_server(token):
    """Enable livepatch with the specified token."""
    logger.info("Enabling livepatch on-prem server using auth token")
    result = subprocess.run(
        ["canonical-livepatch", "enable", token], capture_output=True, text=True
    )
    if result.returncode != 0:
        logger.error("Error running canonical-livepatch enable: %s", result.stderr)
        raise ProcessExecutionError(result.args, result.returncode, result.stdout, result.stderr)


def install_livepatch():
    """Install the canonical-livepatch package."""
    logger.info("Installing package canonical-livepatch")
    subprocess.check_call(["sudo", "snap", "install", "canonical-livepatch"])


def disable_canonical_livepatch():
    """Disable the canonical-livepatch."""
    result = subprocess.run(["canonical-livepatch", "disable"], capture_output=True, text=True)
    if result.returncode != 0:
        logger.error("Error running canonical-livepatch disable: %s", result.stderr)
        raise ProcessExecutionError(result.args, result.returncode, result.stdout, result.stderr)


def ua_enable_service(service):
    """Enable a ubuntu-advantage service."""
    subprocess.check_call(["ubuntu-advantage", "enable", service])


def parse_services(services_str):
    """Parse a comma-separated string of services into a list."""
    return (
        [service.strip() for service in services_str.split(",") if service.strip() != ""]
        if services_str and services_str.strip() != ""
        else None
    )


@contextmanager
def create_attach_config(token, services=None):
    """Create an attach config file with the specified token."""
    attach_config = {"token": token, "enable_services": services}
    try:
        with NamedTemporaryFile(mode="w", suffix=".yaml", prefix="pro_attach", dir="/tmp") as f:
            yaml.dump(attach_config, f, default_flow_style=False)
            temp_file_path = f.name
            logger.info("Created attach config file: %s", temp_file_path)
            yield temp_file_path
    except IOError as e:
        logger.error("Error creating attach config file: %s", str(e))
        raise e


@retry(ProcessExecutionError)
def attach_subscription(token, services=None):
    """Attach an ubuntu-advantage subscription using the specified token and services."""
    if services:
        with create_attach_config(token, services) as attach_config_path:
            result = subprocess.run(
                ["ubuntu-advantage", "attach", "--attach-config", attach_config_path],
                capture_output=True,
                text=True,
            )
    else:
        result = subprocess.run(
            ["ubuntu-advantage", "attach", token], capture_output=True, text=True
        )
    if result.returncode != 0:
        logger.error("Error running attach. stderr %s\nstdout: %s", result.stderr, result.stdout)
        raise ProcessExecutionError(result.args, result.returncode, result.stdout, result.stderr)


@retry(ProcessExecutionError)
def get_status_output():
    """Return the parsed output from ubuntu-advantage status."""
    result = subprocess.run(
        ["ubuntu-advantage", "status", "--all", "--format", "json"], capture_output=True, text=True
    )
    if result.returncode != 0:
        logger.error("Error running attach. stderr %s\nstdout: %s", result.stderr, result.stdout)
        raise ProcessExecutionError(result.args, result.returncode, result.stdout, result.stderr)
    output = result.stdout
    # handle different return type from xenial
    if isinstance(output, bytes):
        output = output.decode("utf-8")
    return json.loads(output)


def get_enabled_services(status):
    """Return a list of enabled services."""
    services = []
    for service in status.get("services"):
        if service.get("status") == "enabled":
            services.append(service.get("name"))
    return services


class UbuntuAdvantageCharm(CharmBase):
    """Charm to handle ubuntu-advantage installation and configuration."""

    _state = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        self._setup_proxy_env()
        self._state.set_default(
            contract_url=None,
            hashed_token=None,
            package_needs_installing=True,
            ppa=None,
            livepatch_needs_installing=True,
        )

        self.framework.observe(self.on.config_changed, self.config_changed)

    def _setup_proxy_env(self):
        """Setup proxy variables from model."""
        self.env = dict(os.environ)
        self.env["http_proxy"] = self.config.get("override-http-proxy") or self.env.get(
            "JUJU_CHARM_HTTP_PROXY", ""
        )
        self.env["https_proxy"] = self.config.get("override-https-proxy") or self.env.get(
            "JUJU_CHARM_HTTPS_PROXY", ""
        )
        self.env["no_proxy"] = self.env.get("JUJU_CHARM_NO_PROXY", "")

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
        """Install and configure ubuntu-advantage tools and attachment."""
        logger.info("Beginning config_changed")
        self.unit.status = MaintenanceStatus("Configuring")
        self._setup_proxy_env()
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
        """Install apt package if necessary."""
        if self._state.package_needs_installing:
            logger.info("Installing package ubuntu-advantage-tools")
            apt.add_package("ubuntu-advantage-tools", update_cache=True)
            self._state.package_needs_installing = False

    def _configure_livepatch(self):
        """Configure the onprem livepatch server and token."""
        livepatch_server = self.config.get("livepatch_server_url", "").strip()
        livepatch_token = self.config.get("livepatch_token", "").strip()

        if self._state.livepatch_needs_installing:
            install_livepatch()
            self._state.livepatch_needs_installing = False

        try:
            if livepatch_server and livepatch_token:
                set_livepatch_server(livepatch_server)
                enable_livepatch_server(livepatch_token)
            else:
                # Set to default server
                status = get_status_output()
                is_attached = status.get("attached")
                enabled_services = get_enabled_services(status)
                logger.info("Setting livepatch on-prem server to default")
                set_livepatch_server("https://livepatch.canonical.com")
                disable_canonical_livepatch()
                if is_attached and "livepatch" in enabled_services:
                    logger.info("Enabling livepatch hosted server using Pro client")
                    ua_enable_service("livepatch")
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

        try:
            status = get_status_output()
        except ProcessExecutionError as e:
            self.unit.status = BlockedStatus(str(e))
            return
        if status["attached"] and (config_changed or token_changed):
            detach_subscription()
            self._state.hashed_token = None

        if not token:
            self.unit.status = BlockedStatus("No token configured")
            return
        elif config_changed or token_changed:
            logger.info("Attaching ubuntu-advantage subscription")
            try:
                enable_services = parse_services(self.config.get("services", "").strip())
                attach_subscription(token, services=enable_services)
            except ProcessExecutionError as e:
                self.unit.status = BlockedStatus(str(e))
                return
            self._state.hashed_token = hashed_token

    def _handle_status_state(self):
        """Parse status output to determine which services are active."""
        status = get_status_output()
        services = get_enabled_services(status)
        message = "Attached (" + ",".join(services) + ")"
        self.unit.status = ActiveStatus(message)

    def _configure_ua_proxy(self):
        """Configure the proxy options for the ubuntu-advantage client."""
        for config_key in ("http_proxy", "https_proxy"):
            if self.env[config_key]:
                subprocess.check_call(
                    [
                        "ubuntu-advantage",
                        "config",
                        "set",
                        "{}={}".format(config_key, self.env[config_key]),
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
