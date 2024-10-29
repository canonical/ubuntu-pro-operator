# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Canonical livepatch functions."""

import logging
import subprocess

from exceptions import ProcessExecutionError

logger = logging.getLogger(__name__)


def set_livepatch_server(server):
    """Set the livepatch server."""
    logger.info("Setting livepatch on-prem server")
    result = subprocess.run(
        ["canonical-livepatch", "config", f"remote-server={server}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        stdout = (
            result.stdout.decode("utf-8", errors="ignore")
            if isinstance(result.stdout, bytes)
            else result.stdout
        )
        stderr = (
            result.stderr.decode("utf-8", errors="ignore")
            if isinstance(result.stderr, bytes)
            else result.stderr
        )
        logger.error("Error setting canonical-livepatch server: %s", stderr)
        raise ProcessExecutionError(result.args, result.returncode, stdout, stderr)


def enable_livepatch_server(token):
    """Enable livepatch with the specified token."""
    logger.info("Enabling livepatch on-prem server using auth token")
    result = subprocess.run(
        ["canonical-livepatch", "enable", token], stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    if result.returncode != 0:
        stdout = (
            result.stdout.decode("utf-8", errors="ignore")
            if isinstance(result.stdout, bytes)
            else result.stdout
        )
        stderr = (
            result.stderr.decode("utf-8", errors="ignore")
            if isinstance(result.stderr, bytes)
            else result.stderr
        )
        logger.error("Error running canonical-livepatch enable: %s", stderr)
        raise ProcessExecutionError(result.args, result.returncode, stdout, stderr)


def install_livepatch():
    """Install the canonical-livepatch package."""
    logger.info("Installing package canonical-livepatch")
    subprocess.check_call(["snap", "install", "canonical-livepatch"])


def disable_canonical_livepatch():
    """Disable the canonical-livepatch."""
    result = subprocess.run(
        ["canonical-livepatch", "disable"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    if result.returncode != 0:
        stdout = (
            result.stdout.decode("utf-8", errors="ignore")
            if isinstance(result.stdout, bytes)
            else result.stdout
        )
        stderr = (
            result.stderr.decode("utf-8", errors="ignore")
            if isinstance(result.stderr, bytes)
            else result.stderr
        )
        logger.error("Error running canonical-livepatch disable: %s", stderr)
        raise ProcessExecutionError(result.args, result.returncode, stdout, stderr)
