import json
import os
import unittest
from unittest.mock import patch

from statsig import StatsigServer, StatsigOptions, StatsigUser
from tests.network_stub import NetworkStub

with open(os.path.join(os.path.abspath(os.path.dirname(__file__)),
                       '../testdata/download_config_specs_with_sdk_configs.json')) as r:
    CONFIG_SPECS_RESPONSE = r.read()


class DCSOverrideTest(unittest.TestCase):
    _network_stub = NetworkStub("http://override-log-event-interval-test")

    @patch('requests.Session.request', side_effect=_network_stub.mock)
    def setUp(self, mock_request):
        self._instance = StatsigServer()
        options = StatsigOptions(
            api="http://override-log-event-interval-test",
            disable_diagnostics=True,
        )

        self._network_stub.reset()

        self._network_stub.stub_request_with_value("download_config_specs/.*", 200, json.loads(CONFIG_SPECS_RESPONSE))

        self._network_stub.stub_request_with_value("log_event", 202, {})

        self._instance.initialize("secret-key", options)
        self._user = StatsigUser("dloomb")
        self.flush()

    @patch('requests.Session.request', side_effect=_network_stub.mock)
    def flush(self, mock_request):
        self._instance.flush()

    @patch('requests.Session.request', side_effect=_network_stub.mock)
    def test_interval_is_overridden(self, mock_request):
        self.assertEqual(self._instance._logger._logger_worker._log_interval, 100.0)
