import time
import unittest

from unittest.mock import patch
from tests.network_stub import NetworkStub
from statsig.utils import logger
from statsig import StatsigOptions, statsig

_network_stub = NetworkStub("http://test-output-logger")


class TestOutputLogger(unittest.TestCase):

    @classmethod
    @patch('requests.post', side_effect=_network_stub.mock)
    def setUpClass(cls, mock_post):
        _network_stub.reset()

        def dcs_callback(url: str, data: dict):
            time.sleep(1.5)
            raise Exception("Network request failed")

        _network_stub.stub_request_with_function(
            "download_config_specs", 500, dcs_callback)

    def tearDown(self):
        statsig.shutdown()
        logger.clear_log_history()

    @patch('requests.post', side_effect=_network_stub.mock)
    def test_initialize_timeout(self, mock_post):
        options = StatsigOptions(api=_network_stub.host, init_timeout=1)
        statsig.initialize("secret-key", options)
        self.assertTrue(len(logger._logs.get("Initialize")) > 3)

    @patch('requests.post', side_effect=_network_stub.mock)
    def test_initialize_failed_to_load_network(self, mock_post):
        options = StatsigOptions(api=_network_stub.host)
        statsig.initialize("secret-key", options)
        self.assertTrue(len(logger._logs.get("Initialize")) > 2)
        self.assertTrue(len(logger._logs.get("warning")) > 0)