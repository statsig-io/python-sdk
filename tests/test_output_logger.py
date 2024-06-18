from collections import defaultdict
import time
import unittest

from unittest.mock import patch
from network_stub import NetworkStub
from statsig import statsig, StatsigOptions, OutputLogger

_network_stub = NetworkStub("http://test-output-logger")

class MockOutputLogger(OutputLogger):
    def __init__(self):
        super().__init__('mock')
        self._logs = defaultdict(list)
        self._urls = []

    def log_process(self, process: str, msg: str):
        message = f"{process}: {msg}"
        self.info(message)

    def debug(self, msg, *args, **kwargs):
        self.add_url(args)
        self._logs['debug'].append(msg)

    def info(self, msg, *args, **kwargs):
        self.add_url(args)
        self._logs['info'].append(msg)

    def warning(self, msg, *args, **kwargs):
        self.add_url(args)
        self._logs['warning'].append(msg)

    def add_url(self, args):
        for arg in args:
            if isinstance(arg, str) and arg.startswith('http://test-output-logger'):
                self._urls.append(arg)

    def check_urls_for_secret(self):
        failed_urls = []
        for url in self._urls:
            if 'secret-' in url:
                failed_urls.append(url)
        return failed_urls

class TestOutputLogger(unittest.TestCase):

    @classmethod
    @patch('requests.request', side_effect=_network_stub.mock)
    def setUpClass(cls, mock_request):
        _network_stub.reset()

        def dcs_callback(url: str, **kwargs):
            time.sleep(0.2)

        _network_stub.stub_request_with_function(
            "download_config_specs/.*", 404, dcs_callback)

    def tearDown(self):
        statsig.shutdown()

    @patch('requests.request', side_effect=_network_stub.mock)
    def test_initialize_timeout(self, mock_request):
        logger = MockOutputLogger()
        options = StatsigOptions(api=_network_stub.host, init_timeout=0.1, disable_diagnostics=True, custom_logger=logger)
        statsig.initialize("secret-key", options)
        self.assertGreater(len(logger._logs.get("info")), 3)

    @patch('requests.request', side_effect=_network_stub.mock)
    def test_initialize_failed_to_load_network(self, mock_request):
        logger = MockOutputLogger()
        options = StatsigOptions(api=_network_stub.host, disable_diagnostics=True, custom_logger=logger)
        statsig.initialize("secret-key", options)
        self.assertGreater(len(logger._logs.get("info")), 2)
        self.assertGreater(len(logger._logs.get("warning")), 0)
        failed_urls = logger.check_urls_for_secret()
        self.assertEqual(len(failed_urls), 0)
