import json
import os
import random
import string
import unittest
from unittest.mock import patch

from gzip_helpers import GzipHelpers
from network_stub import NetworkStub
from statsig import statsig, StatsigUser, StatsigOptions, StatsigEnvironmentTier

with open(os.path.join(os.path.abspath(os.path.dirname(__file__)), '../testdata/download_config_specs.json')) as r:
    CONFIG_SPECS_RESPONSE = r.read()
PARSED_CONFIG_SPEC = json.loads(CONFIG_SPECS_RESPONSE)

_network_stub = NetworkStub("http://test-sampling")


def generate_random_user_id(length=12):
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))


@patch('requests.request', side_effect=_network_stub.mock)
class TestEventSampling(unittest.TestCase):
    _events = []

    @classmethod
    @patch('requests.request', side_effect=_network_stub.mock)
    def setUpClass(cls, mock_request):
        _network_stub.stub_request_with_value(
            "download_config_specs/.*", 200, PARSED_CONFIG_SPEC)

        def log_event_callback(url: str, **kwargs):
            new_events = GzipHelpers.decode_body(kwargs)["events"]
            cls._events.extend(new_events)

        _network_stub.stub_request_with_function(
            "log_event", 202, log_event_callback)

        cls.statsig_user = StatsigUser(
            "regular_user_id", email="testuser@statsig.com")
        cls.random_user = StatsigUser("random")
        cls._events = []

    def setUp(self):
        self.__class__._events = []

    def test_samples_production(self, mock_request):
        options = StatsigOptions(
            api=_network_stub.host,
            tier=StatsigEnvironmentTier.production,
            disable_diagnostics=True)
        statsig.initialize("secret-key", options=options)
        gate = statsig.check_gate(self.statsig_user, "always_on_gate_sampled")
        statsig.shutdown()

        self.assertTrue(gate)
        self.assertEqual(0, len(self._events))

    def test_samples_production_metadata_1_percent(self, mock_request):
        options = StatsigOptions(
            api=_network_stub.host,
            tier=StatsigEnvironmentTier.production,
            disable_diagnostics=True)
        statsig.initialize("secret-key", options=options)
        for i in range(10000):
            user = StatsigUser(generate_random_user_id())
            statsig.check_gate(user, "always_on_gate_sampled")
        statsig.shutdown()
        print("Expecting around 100 events, received", len(self._events))
        self.assertTrue(90 <= len(self._events) <= 110)
        sampled_event = self._events[0]
        self.assertEqual(sampled_event["statsigMetadata"]["samplingRate"], 101)

    def test_samples_production_metadata_10_percent(self, mock_request):
        options = StatsigOptions(
            api=_network_stub.host,
            tier=StatsigEnvironmentTier.production,
            disable_diagnostics=True)
        statsig.initialize("secret-key", options=options)
        for i in range(10000):
            user = StatsigUser(generate_random_user_id())
            statsig.check_gate(user, "always_on_gate_sampled_10_percent")
        statsig.shutdown()
        print("Expecting around 1000 events, received", len(self._events))
        self.assertTrue(900 <= len(self._events) <= 1100)
        sampled_event = self._events[0]
        self.assertEqual(sampled_event["statsigMetadata"]["samplingRate"], 10)

    def test_no_sampling_if_not_production(self, mock_request):
        options = StatsigOptions(
            api=_network_stub.host,
            tier=StatsigEnvironmentTier.development,
            disable_diagnostics=True)
        statsig.initialize("secret-key", options=options)
        gate = statsig.check_gate(self.statsig_user, "always_on_gate_sampled")
        statsig.shutdown()

        self.assertTrue(gate)
        self.assertEqual(1, len(self._events))
        sampled_event = self._events[0]
        self.assertEqual(sampled_event["metadata"].get("sampleRate"), None)
