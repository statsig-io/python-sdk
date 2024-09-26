import json
import os
import random
import string
import unittest
from unittest.mock import patch

from gzip_helpers import GzipHelpers
from network_stub import NetworkStub
from statsig import statsig, StatsigUser, StatsigOptions, StatsigEnvironmentTier

with open(os.path.join(os.path.abspath(os.path.dirname(__file__)),
                       '../testdata/download_config_specs_sampling.json')) as r:
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

    def stub_network(self, mock_request, sampling_mode):
        if sampling_mode == "on":
            PARSED_CONFIG_SPEC["sdk_configs"] = {
                "sampling_mode": "on"
            }
        if sampling_mode == "shadow":
            PARSED_CONFIG_SPEC["sdk_configs"] = {
                "sampling_mode": "shadow"
            }
        _network_stub.stub_request_with_value(
            "download_config_specs/.*", 200, PARSED_CONFIG_SPEC)

    def run_configs(self, mock_request):
        statsig.check_gate(self.statsig_user, "always_on_gate")
        statsig.get_config(self.statsig_user, "test_config")
        statsig.get_experiment(self.statsig_user, "sample_experiment")

        statsig.check_gate(self.statsig_user, "always_on_gate_sampled")
        statsig.get_config(self.statsig_user, "test_config_sampled")
        statsig.get_experiment(self.statsig_user, "not_started_exp")

    def test_apply_sampling_if_production(self, mock_request):
        options = StatsigOptions(
            api=_network_stub.host,
            tier=StatsigEnvironmentTier.production,
            disable_diagnostics=True)
        self.stub_network(mock_request, "on")
        statsig.initialize("secret-key", options=options)
        self.run_configs(mock_request)
        statsig.shutdown()

        not_sampled_event = self._events[0]
        self.assertEqual(not_sampled_event["statsigMetadata"].get("sampleRate"), None)
        self.assertEqual(not_sampled_event["statsigMetadata"].get("samplingMode"), 'on')
        self.assertEqual(3, len(self._events))

    def test_do_not_apply_sampling_if_development(self, mock_request):
        options = StatsigOptions(
            api=_network_stub.host,
            tier=StatsigEnvironmentTier.development,
            disable_diagnostics=True)
        self.stub_network(mock_request, "on")
        statsig.initialize("secret-key", options=options)
        self.run_configs(mock_request)
        statsig.shutdown()

        self.assertEqual(6, len(self._events))
        not_sampled_event = self._events[0]
        self.assertEqual(not_sampled_event["statsigMetadata"].get("sampleRate"), None)
        self.assertEqual(not_sampled_event["statsigMetadata"].get("samplingMode"), 'on')

    def test_do_not_apply_sampling_if_staging(self, mock_request):
        options = StatsigOptions(
            api=_network_stub.host,
            tier=StatsigEnvironmentTier.staging,
            disable_diagnostics=True)
        self.stub_network(mock_request, "on")
        statsig.initialize("secret-key", options=options)
        self.run_configs(mock_request)
        statsig.shutdown()

        self.assertEqual(6, len(self._events))
        not_sampled_event = self._events[0]
        self.assertEqual(not_sampled_event["statsigMetadata"].get("sampleRate"), None)
        self.assertEqual(not_sampled_event["statsigMetadata"]["samplingMode"], 'on')

    def test_apply_1_percent_sampling(self, mock_request):
        options = StatsigOptions(
            api=_network_stub.host,
            tier=StatsigEnvironmentTier.production,
            disable_diagnostics=True)
        self.stub_network(mock_request, "on")
        statsig.initialize("secret-key", options=options)
        for i in range(10000):
            user = StatsigUser(generate_random_user_id())
            statsig.check_gate(user, "always_on_gate_sampled")
        statsig.shutdown()
        print("Expecting around 100 events, received", len(self._events))
        self.assertTrue(85 <= len(self._events) <= 115)
        sampled_event = self._events[0]
        self.assertEqual(sampled_event["statsigMetadata"]["samplingRate"], 101)

    def test_apply_10_percent_sampling(self, mock_request):
        options = StatsigOptions(
            api=_network_stub.host,
            tier=StatsigEnvironmentTier.production,
            disable_diagnostics=True)
        self.stub_network(mock_request, "on")
        statsig.initialize("secret-key", options=options)
        for i in range(10000):
            user = StatsigUser(generate_random_user_id())
            statsig.check_gate(user, "always_on_gate_sampled_10_percent")
        statsig.shutdown()
        print("Expecting around 1000 events, received", len(self._events))
        self.assertTrue(900 <= len(self._events) <= 1100)
        sampled_event = self._events[0]
        self.assertEqual(sampled_event["statsigMetadata"]["samplingRate"], 10)

    def test_apply_shadow_sampling_in_production_dropped(self, mock_request):
        options = StatsigOptions(
            api=_network_stub.host,
            tier=StatsigEnvironmentTier.production,
            disable_diagnostics=True)
        self.stub_network(mock_request, "shadow")
        statsig.initialize("secret-key", options=options)
        statsig.check_gate(self.statsig_user, "always_on_gate_sampled")
        statsig.check_gate(self.statsig_user, "always_on_gate")

        statsig.shutdown()

        self.assertEqual(2, len(self._events))
        sampled_event = self._events[0]
        self.assertEqual(sampled_event["statsigMetadata"]["samplingRate"], 101)
        self.assertEqual(sampled_event["statsigMetadata"]["shadowLogged"], "dropped")
        self.assertEqual(sampled_event["statsigMetadata"]["samplingMode"], 'shadow')
        not_sampled_event = self._events[1]
        self.assertEqual(not_sampled_event["statsigMetadata"].get("sampleRate"), None)
        self.assertEqual(not_sampled_event["statsigMetadata"].get("shadowLogged"), None)
        self.assertEqual(not_sampled_event["statsigMetadata"]["samplingMode"], "shadow")

    def test_apply_shadow_sampling_in_production_logged(self, mock_request):
        options = StatsigOptions(
            api=_network_stub.host,
            tier=StatsigEnvironmentTier.production,
            disable_diagnostics=True)
        self.stub_network(mock_request, "shadow")
        statsig.initialize("secret-key", options=options)
        for i in range(100):
            user = StatsigUser(generate_random_user_id())
            statsig.check_gate(user, "always_on_gate_sampled_10_percent")

        statsig.shutdown()

        self.assertEqual(100, len(self._events))
        shadow_logged_events = [event for event in self._events if
                                event.get("statsigMetadata", {}).get("shadowLogged") == "logged"]

        self.assertGreater(len(shadow_logged_events), 0)
        shadow_logged_event = shadow_logged_events[0]

        self.assertEqual(shadow_logged_event["statsigMetadata"]["samplingRate"], 10)
        self.assertEqual(shadow_logged_event["statsigMetadata"]["shadowLogged"], "logged")
        self.assertEqual(shadow_logged_event["statsigMetadata"]["samplingMode"], "shadow")

    def test_do_not_apply_shadow_sampling_in_development(self, mock_request):
        options = StatsigOptions(
            api=_network_stub.host,
            tier=StatsigEnvironmentTier.development,
            disable_diagnostics=True)
        self.stub_network(mock_request, "shadow")
        statsig.initialize("secret-key", options=options)
        statsig.check_gate(self.statsig_user, "always_on_gate_sampled")
        statsig.check_gate(self.statsig_user, "always_on_gate")

        statsig.shutdown()

        self.assertEqual(2, len(self._events))
        sampled_event = self._events[0]
        self.assertEqual(sampled_event["metadata"].get("sampleRate"), None)
        self.assertEqual(sampled_event["metadata"].get("shadowLogged"), None)
        self.assertEqual(sampled_event["statsigMetadata"]["samplingMode"], "shadow")

        not_sampled_event = self._events[1]
        self.assertEqual(not_sampled_event["statsigMetadata"].get("sampleRate"), None)
        self.assertEqual(not_sampled_event["statsigMetadata"].get("shadowLogged"), None)
        self.assertEqual(not_sampled_event["statsigMetadata"]["samplingMode"], "shadow")

    def test_do_not_apply_shadow_sampling_in_staging(self, mock_request):
        options = StatsigOptions(
            api=_network_stub.host,
            tier=StatsigEnvironmentTier.staging,
            disable_diagnostics=True)
        self.stub_network(mock_request, "shadow")
        statsig.initialize("secret-key", options=options)
        statsig.check_gate(self.statsig_user, "always_on_gate_sampled")
        statsig.check_gate(self.statsig_user, "always_on_gate")

        statsig.shutdown()

        self.assertEqual(2, len(self._events))
        sampled_event = self._events[0]
        self.assertEqual(sampled_event["statsigMetadata"].get("sampleRate"), None)
        self.assertEqual(sampled_event["statsigMetadata"].get("shadowLogged"), None)
        self.assertEqual(sampled_event["statsigMetadata"]["samplingMode"], "shadow")

        not_sampled_event = self._events[1]
        self.assertEqual(not_sampled_event["statsigMetadata"].get("sampleRate"), None)
        self.assertEqual(not_sampled_event["statsigMetadata"].get("shadowLogged"), None)
        self.assertEqual(not_sampled_event["statsigMetadata"]["samplingMode"], "shadow")
