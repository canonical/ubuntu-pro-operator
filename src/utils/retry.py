# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Utility functions for the Ubuntu Pro charm."""

import logging
import time
from functools import wraps

logger = logging.getLogger(__name__)

RETRY_SLEEPS = [0.5, 1, 2]


def retry(exception):
    """Decorator to retry on exception multiple times with a sleep in between."""

    def wrapper(func):
        @wraps(func)
        def decorator(*args, **kwargs):
            for idx, sleep_time in enumerate(RETRY_SLEEPS):
                try:
                    return func(*args, **kwargs)
                except exception as e:
                    remaining_retries = len(RETRY_SLEEPS) - idx - 1
                    if remaining_retries == 0:
                        raise e
                    logger.warning("%s: Retrying %d more times.", str(e), remaining_retries)
                    time.sleep(sleep_time)

        return decorator

    return wrapper
