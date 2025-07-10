import logging
import time
import unittest
from collections import defaultdict
from unittest.mock import patch

from network_stub import NetworkStub
from statsig import statsig, StatsigOptions, OutputLogger
from statsig.output_logger import sanitize, LogLevel

_network_stub = NetworkStub("http://test-output-logger")


class MockOutputLogger(OutputLogger):
    def __init__(self):
        super().__init__('mock')
        self._disabled = False
        self._logs = defaultdict(list)
        self._urls = []

    def log_process(self, process: str, msg: str):
        message = sanitize(f"{process}: {msg}")
        self.debug(message)

    def debug(self, msg, *args, **kwargs):
        if self._logger.isEnabledFor(logging.DEBUG) and not self._disabled:
            sanitized_msg, sanitized_args, sanitized_kwargs = self._sanitize_args(msg, *args, **kwargs)
            self.add_url(sanitized_args)
            self._logs['debug'].append(sanitized_msg)

    def info(self, msg, *args, **kwargs):
        if self._logger.isEnabledFor(logging.INFO) and not self._disabled:
            sanitized_msg, sanitized_args, sanitized_kwargs = self._sanitize_args(msg, *args, **kwargs)
            self.add_url(sanitized_args)
            self._logs['info'].append(sanitized_msg)

    def warning(self, msg, *args, **kwargs):
        if self._logger.isEnabledFor(logging.WARNING) and not self._disabled:
            sanitized_msg, sanitized_args, sanitized_kwargs = self._sanitize_args(msg, *args, **kwargs)
            self.add_url(sanitized_args)
            self._logs['warning'].append(sanitized_msg)

    def error(self, msg, *args, **kwargs):
        if self._logger.isEnabledFor(logging.ERROR) and not self._disabled:
            sanitized_msg, sanitized_args, sanitized_kwargs = self._sanitize_args(msg, *args, **kwargs)
            self.add_url(sanitized_args)
            self._logs['error'].append(sanitized_msg)

    def _sanitize_args(self, msg, *args, **kwargs):
        sanitized_msg = sanitize(msg)
        sanitized_args = tuple(sanitize(str(arg)) for arg in args)
        sanitized_kwargs = {k: sanitize(str(v)) for k, v in kwargs.items()}
        return sanitized_msg, sanitized_args, sanitized_kwargs

    def add_url(self, args):
        for arg in args:
            if isinstance(arg, str) and arg.startswith('http://test-output-logger'):
                self._urls.append(arg)

    def check_urls_for_secret(self, key):
        failed_urls = []
        for url in self._urls:
            if key in url:
                failed_urls.append(url)
        return failed_urls


class TestOutputLogger(unittest.TestCase):

    @classmethod
    @patch('requests.Session.request', side_effect=_network_stub.mock)
    def setUpClass(cls, mock_request):
        _network_stub.reset()

        def dcs_callback(url: str, **kwargs):
            time.sleep(0.2)

        _network_stub.stub_request_with_function(
            "download_config_specs/.*", 404, dcs_callback)

    def tearDown(self):
        statsig.shutdown()

    @patch('requests.Session.request', side_effect=_network_stub.mock)
    def test_initialize_timeout(self, mock_request):
        logger = MockOutputLogger()
        logger.set_log_level(LogLevel.INFO)
        options = StatsigOptions(api=_network_stub.host, init_timeout=0.1, disable_diagnostics=True,
                                 custom_logger=logger)
        statsig.initialize("secret-key", options)
        self.assertGreaterEqual(len(logger._logs.get("info")), 2)

    @patch('requests.Session.request', side_effect=_network_stub.mock)
    def test_initialize_failed_to_load_network_info(self, mock_request):
        logger = MockOutputLogger()
        logger.set_log_level(LogLevel.INFO)
        options = StatsigOptions(api=_network_stub.host, disable_diagnostics=True, custom_logger=logger)
        statsig.initialize("secret-key", options)
        self.assertGreaterEqual(len(logger._logs.get("info")), 2)
        self.assertGreater(len(logger._logs.get("warning")), 0)
        failed_urls = logger.check_urls_for_secret('secret-key')
        self.assertEqual(len(failed_urls), 0)

    @patch('requests.Session.request', side_effect=_network_stub.mock)
    def test_set_logging_level_warning(self, mock_request):
        logger = MockOutputLogger()
        logger.set_log_level(LogLevel.WARNING)
        options = StatsigOptions(api=_network_stub.host, disable_diagnostics=True, custom_logger=logger)
        statsig.initialize("secret-key", options)
        self.assertIsNone(logger._logs.get("info"))
        self.assertGreater(len(logger._logs.get("warning")), 0)
        failed_urls = logger.check_urls_for_secret('secret-key')
        self.assertEqual(len(failed_urls), 0)

    @patch('requests.Session.request', side_effect=_network_stub.mock)
    def test_set_logging_level_debug(self, mock_request):
        logger = MockOutputLogger()
        logger.set_log_level(LogLevel.DEBUG)
        options = StatsigOptions(api=_network_stub.host, disable_diagnostics=True, custom_logger=logger)
        statsig.initialize("secret-key", options)
        self.assertGreater(len(logger._logs.get("debug")), 0)
        self.assertGreater(len(logger._logs.get("info")), 0)
        self.assertGreater(len(logger._logs.get("warning")), 0)
        failed_urls = logger.check_urls_for_secret('secret-key')
        self.assertEqual(len(failed_urls), 0)
