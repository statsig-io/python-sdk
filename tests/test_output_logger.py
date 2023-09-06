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

    def log_process(self, process: str, msg: str):
        message = f"{process}: {msg}"
        self.info(message)

    def debug(self, msg, *args, **kwargs):
        self._logs['debug'].append(msg)

    def info(self, msg, *args, **kwargs):
        self._logs['info'].append(msg)

    def warning(self, msg, *args, **kwargs):
        self._logs['warning'].append(msg)

class TestOutputLogger(unittest.TestCase):

    @classmethod
    @patch('requests.post', side_effect=_network_stub.mock)
    def setUpClass(cls, mock_post):
        _network_stub.reset()

        def dcs_callback(url: str, data: dict):
            time.sleep(0.2)
            raise Exception("Network request failed")

        _network_stub.stub_request_with_function(
            "download_config_specs", 500, dcs_callback)

    def tearDown(self):
        statsig.shutdown()

    @patch('requests.post', side_effect=_network_stub.mock)
    def test_initialize_timeout(self, mock_post):
        logger = MockOutputLogger()
        options = StatsigOptions(api=_network_stub.host, init_timeout=0.1, disable_diagnostics=True, custom_logger=logger)
        statsig.initialize("secret-key", options)
        self.assertGreater(len(logger._logs.get("info")), 3)

    @patch('requests.post', side_effect=_network_stub.mock)
    def test_initialize_failed_to_load_network(self, mock_post):
        logger = MockOutputLogger()
        options = StatsigOptions(api=_network_stub.host, disable_diagnostics=True, custom_logger=logger)
        statsig.initialize("secret-key", options)
        self.assertGreater(len(logger._logs.get("info")), 2)
        self.assertGreater(len(logger._logs.get("warning")), 0)
