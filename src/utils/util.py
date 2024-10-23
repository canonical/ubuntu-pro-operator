# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Utility functions for the Ubuntu Pro charm."""


import yaml


def update_configuration(contract_url):
    """Write the contract_url to the uaclient configuration file."""
    with open("/etc/ubuntu-advantage/uaclient.conf", "r+") as f:
        client_config = yaml.safe_load(f)
        client_config["contract_url"] = contract_url
        f.seek(0)
        yaml.dump(client_config, f)
        f.truncate()


def parse_services(services_str):
    """Parse a comma-separated string of services into a list."""
    return (
        [service.strip() for service in services_str.split(",") if service.strip() != ""]
        if services_str and services_str.strip() != ""
        else None
    )
