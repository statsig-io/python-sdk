import time
import unittest

from unittest.mock import patch
from network_stub import NetworkStub
from statsig.utils import logger
from statsig import StatsigOptions, statsig

_network_stub = NetworkStub("http://test-output-logger")


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

        logger._capture_logs = True

    @classmethod
    def tearDownClass(cls) -> None:
        logger._capture_logs = False

    def tearDown(self):
        statsig.shutdown()
        logger.clear_log_history()

    @patch('requests.post', side_effect=_network_stub.mock)
    def test_initialize_timeout(self, mock_post):
        options = StatsigOptions(api=_network_stub.host, init_timeout=0.1, disable_diagnostics=True)
        statsig.initialize("secret-key", options)
        self.assertGreater(len(logger._logs.get("Initialize")), 3)

    @patch('requests.post', side_effect=_network_stub.mock)
    def test_initialize_failed_to_load_network(self, mock_post):
        options = StatsigOptions(api=_network_stub.host, disable_diagnostics=True)
        statsig.initialize("secret-key", options)
        self.assertGreater(len(logger._logs.get("Initialize")), 2)
        self.assertGreater(len(logger._logs.get("warning")), 0)
