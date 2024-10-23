from uaclient.api.u.pro.attach.token.full_token_attach.v1 import (
    FullTokenAttachOptions,
    full_token_attach,
)
from uaclient.api.u.pro.detach.v1 import detach
from uaclient.api.u.pro.services.enable.v1 import EnableOptions, enable
from uaclient.api.u.pro.status.enabled_services.v1 import enabled_services
from uaclient.api.u.pro.status.is_attached.v1 import is_attached

from exceptions import ProcessExecutionError
from utils import retry


# Add error handling to all functions
def attach_status():
    return is_attached().is_attached


def detach_sub():
    return detach()


def enable_service(service):
    options = EnableOptions(service=service)
    return enable(options)


def get_enabled_services():
    services = enabled_services()
    return [s.name for s in services.enabled_services]


def attach_sub(token, enable_services=None, auto_enable=False):
    if enable_services:
        options = FullTokenAttachOptions(token=token, auto_enable_services=False)
        res = full_token_attach(options)
        for service in enable_services:
            enable_service(service=service)
        return res
    options = FullTokenAttachOptions(token=token, auto_enable_services=auto_enable)
    return full_token_attach(options)
