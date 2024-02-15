import json
import os
import unittest
import unittest.mock
import time
from statsig import __version__
from unittest.mock import patch
from network_stub import NetworkStub
from statsig import statsig, StatsigUser, StatsigOptions, StatsigEnvironmentTier
from statsig import globals

with open(os.path.join(os.path.abspath(os.path.dirname(__file__)), '../testdata/download_config_specs.json')) as r:
    CONFIG_SPECS_RESPONSE = r.read()

_network_stub = NetworkStub("http://test-retries")


@patch('requests.request', side_effect=_network_stub.mock)
class TestLoggingRetries(unittest.TestCase):

    @classmethod
    @patch('requests.request', side_effect=_network_stub.mock)
    def setUpClass(cls, mock_request):
        _network_stub.stub_request_with_value("download_config_specs/.*", 200, json.loads(CONFIG_SPECS_RESPONSE))

        def on_log(url: str, **kwargs):
            raise ConnectionError

        _network_stub.stub_request_with_function("log_event", 202, on_log)

        cls.statsig_user = StatsigUser(
            "regular_user_id", email="testuser@statsig.com", private_attributes={"test": 123})
        cls.random_user = StatsigUser("random")
        cls._logs = {}
        options = StatsigOptions(
            api=_network_stub.host,
            tier=StatsigEnvironmentTier.development,
            logging_interval=1,
            disable_diagnostics=False)

        statsig.initialize("secret-test", options)
        cls.initTime = round(time.time() * 1000)
        globals.logger._disabled = False

    @classmethod
    def tearDownClass(cls) -> None:
        statsig.shutdown()

    def test_a_check_gate(self, mock_request):
        self.assertEqual(
            statsig.check_gate(self.statsig_user, "always_on_gate"),
            True
        )

        # type: ignore
        statsig.flush()  # it's set at this point
        time.sleep(12)
