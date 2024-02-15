import threading
import time
import os
import unittest
import json

from unittest.mock import patch
from network_stub import NetworkStub
from statsig import StatsigOptions, statsig, StatsigUser

with open(os.path.join(os.path.abspath(os.path.dirname(__file__)), '../testdata/download_config_specs.json')) as r:
    CONFIG_SPECS_RESPONSE = r.read()

MINIMUM_INIT_TIME_S = 2

_network_stub = NetworkStub("http://test-init_timeout")


class TestInitTimeout(unittest.TestCase):

    @classmethod
    @patch('requests.request', side_effect=_network_stub.mock)
    def setUpClass(cls, mock_request):
        _network_stub.reset()

        def dcs_callback(url: str, **kwargs):
            def __work():
                time.sleep(MINIMUM_INIT_TIME_S)

            t = threading.Thread(target=__work)
            t.start()
            t.join(kwargs.get("timeout", None))
            if t.is_alive():
                raise TimeoutError

            return json.loads(CONFIG_SPECS_RESPONSE)

        _network_stub.stub_request_with_function(
            "download_config_specs/.*", 200, dcs_callback)

        cls.test_user = StatsigUser("123", email="testuser@statsig.com")

    def tearDown(self):
        statsig.shutdown()

    @patch('requests.request', side_effect=_network_stub.mock)
    def test_without_timeout_option(self, mock_request):
        options = StatsigOptions(api=_network_stub.host, disable_diagnostics=True)
        start = time.time()
        statsig.initialize("secret-key", options)
        end = time.time()
        self.assertGreater(end - start, MINIMUM_INIT_TIME_S)

    @patch('requests.request', side_effect=_network_stub.mock)
    def test_no_timeout_with_timeout_option(self, mock_request):
        options = StatsigOptions(api=_network_stub.host, init_timeout=5, disable_diagnostics=True)
        start = time.time()
        statsig.initialize("secret-key", options)
        end = time.time()
        self.assertGreater(end - start, MINIMUM_INIT_TIME_S)

    @patch('requests.request', side_effect=_network_stub.mock)
    def test_timeout_with_timeout_option(self, mock_request):
        options = StatsigOptions(api=_network_stub.host, init_timeout=0.1, disable_diagnostics=True)
        start = time.time()
        statsig.initialize("secret-key", options)
        end = time.time()
        self.assertLess(end - start, MINIMUM_INIT_TIME_S)
