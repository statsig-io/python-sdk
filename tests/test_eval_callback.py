import time
import os
import unittest
import json

from typing import Optional, Union, Callable

from unittest.mock import patch
from gzip_helpers import GzipHelpers
from network_stub import NetworkStub
from statsig import statsig, StatsigUser, StatsigOptions, StatsigEvent, StatsigEnvironmentTier, DynamicConfig, Layer, FeatureGate

with open(os.path.join(os.path.abspath(os.path.dirname(__file__)), '../testdata/download_config_specs.json')) as r:
    CONFIG_SPECS_RESPONSE = r.read()

_network_stub = NetworkStub("http://test-statsig-e2e")


@patch('requests.request', side_effect=_network_stub.mock)
class TestEvalCallback(unittest.TestCase):
    _logs = {}
    _gateName = ""
    _configName = ""
    _layerName = ""

    @classmethod
    @patch('requests.request', side_effect=_network_stub.mock)
    def setUpClass(cls, mock_request):
        _network_stub.stub_request_with_value(
            "download_config_specs/.*", 200, json.loads(CONFIG_SPECS_RESPONSE))
        _network_stub.stub_request_with_value("list_1", 200, "+7/rrkvF6\n")
        _network_stub.stub_request_with_value("get_id_lists", 200, {"list_1": {
            "name": "list_1",
            "size": 10,
            "url": _network_stub.host + "/list_1",
            "creationTime": 1,
            "fileID": "file_id_1",
        }})

        def log_event_callback(url: str, **kwargs):
            cls._logs = GzipHelpers.decode_body(kwargs)

        _network_stub.stub_request_with_function(
            "log_event", 202, log_event_callback)

        cls.statsig_user = StatsigUser(
            "regular_user_id", email="testuser@statsig.com", private_attributes={"test": 123})
        cls.random_user = StatsigUser("random")
        cls._logs = {}
        def callback_func(config: Union[DynamicConfig, FeatureGate, Layer]):
            if isinstance(config, FeatureGate):
                cls._gateName = config.get_name()
            if isinstance(config, DynamicConfig):
                cls._configName = config.get_name()
            if isinstance(config, Layer):
                cls._layerName = config.get_name()
                
        options = StatsigOptions(
            api=_network_stub.host,
            tier=StatsigEnvironmentTier.development,
            disable_diagnostics=True,
            evaluation_callback=callback_func)

        statsig.initialize("secret-key", options)
        cls.initTime = round(time.time() * 1000)

    @classmethod
    def tearDownClass(cls) -> None:
        statsig.shutdown()

    # hacky, yet effective. python runs tests in alphabetical order.
    def test_a_check_gate(self, mock_request):
        statsig.check_gate(self.statsig_user, "always_on_gate"),
        self.assertEqual(
            self._gateName,
            "always_on_gate"
        )
        statsig.check_gate(self.statsig_user, "on_for_statsig_email"),
        self.assertEqual(
            self._gateName,
            "on_for_statsig_email"
        )

    def test_b_dynamic_config(self, mock_request):
        statsig.get_config(self.statsig_user, "test_config")
        self.assertEqual(
            self._configName,
            "test_config"
        )

    def test_c_experiment(self, mock_request):
        statsig.get_experiment(self.statsig_user, "sample_experiment")
        self.assertEqual(
            self._configName,
            "sample_experiment"
        )

    def test_c_experiment(self, mock_request):
        config = statsig.get_layer(self.statsig_user, "a_layer")
        self.assertEqual(
            self._layerName,
            "a_layer"
        )

if __name__ == '__main__':
    unittest.main()
