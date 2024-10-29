# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Pro client api related functions."""

from uaclient.api.u.pro.attach.token.full_token_attach.v1 import (
    FullTokenAttachOptions,
    full_token_attach,
)
from uaclient.api.u.pro.detach.v1 import detach
from uaclient.api.u.pro.services.enable.v1 import EnableOptions, enable
from uaclient.api.u.pro.status.enabled_services.v1 import enabled_services
from uaclient.api.u.pro.status.is_attached.v1 import is_attached

from exceptions import APIError
from utils import retry


# Add error handling to all functions
def attach_status():
    """Check if system is attached to Ubuntu Pro subscription."""
    res = is_attached()
    if res.get("errors", None):
        raise APIError(error_code=res["errors"][0]["code"], message=res["errors"][0]["title"])
    return res.is_attached


def detach_sub():
    """Detach system from Ubuntu Pro subscription."""
    res = detach()
    if res.get("errors", None):
        raise APIError(error_code=res["errors"][0]["code"], message=res["errors"][0]["title"])
    return res


def enable_service(service):
    """Enable a specific Ubuntu Pro service."""
    options = EnableOptions(service=service)
    res = enable(options)
    if res.get("errors", None):
        raise APIError(error_code=res["errors"][0]["code"], message=res["errors"][0]["title"])
    return res


def get_enabled_services():
    """Get list of enabled Ubuntu Pro services."""
    services = enabled_services()
    return [s.name for s in services.enabled_services]


@retry(APIError)
def attach_sub(token, enable_services=None, auto_enable=False):
    """Attach system to Ubuntu Pro subscription using token."""
    auto_enable_setting = False if enable_services else auto_enable
    options = FullTokenAttachOptions(token=token, auto_enable_services=auto_enable_setting)
    res = full_token_attach(options)
    if res.get("errors", None):
        raise APIError(error_code=res["errors"][0]["code"], message=res["errors"][0]["title"])
    if enable_services:
        for service in enable_services:
            enable_service(service=service)
    return res
