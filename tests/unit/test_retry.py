# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import time
from unittest import TestCase
from unittest.mock import MagicMock, call, patch

from utils.retry import retry

logger = logging.getLogger(__name__)

RETRY_SLEEPS = [1, 2, 3]


class TestRetryDecorator(TestCase):
    def test_retry_when_success(self):
        @retry(Exception)
        def func():
            return 0

        res = func()
        self.assertEqual(res, 0)

    @patch("time.sleep", MagicMock())
    def test_retry_sleep_calls(self):
        @retry(Exception)
        def func():
            raise Exception("Something went wrong")

        with self.assertRaises(Exception):
            func()

        self.assertEqual(time.sleep.call_count, len(RETRY_SLEEPS) - 1)

    @patch("time.sleep", MagicMock())
    @patch("logging.Logger.warning", MagicMock())
    def test_retry_log_calls(self):
        @retry(Exception)
        def func():
            raise Exception("Something went wrong")

        with self.assertRaises(Exception):
            func()

        self.assertEqual(time.sleep.call_count, len(RETRY_SLEEPS) - 1)
        self.assertEqual(logger.warning.call_count, len(RETRY_SLEEPS) - 1)
        logger.warning.assert_has_calls(
            [call("%s: Retrying %d more times.", "Something went wrong", len(RETRY_SLEEPS) - 1)]
        )
