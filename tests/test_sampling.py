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


@patch('requests.Session.request', side_effect=_network_stub.mock)
class TestEventSampling(unittest.TestCase):
    _events = []

    @classmethod
    @patch('requests.Session.request', side_effect=_network_stub.mock)
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
        if "sdk_configs" not in PARSED_CONFIG_SPEC:
            PARSED_CONFIG_SPEC["sdk_configs"] = {}
        if sampling_mode == "on":
            PARSED_CONFIG_SPEC["sdk_configs"]["sampling_mode"] = "on"
        elif sampling_mode == "shadow":
            PARSED_CONFIG_SPEC["sdk_configs"]["sampling_mode"] = "shadow"
        _network_stub.stub_request_with_value(
            "download_config_specs/.*", 200, PARSED_CONFIG_SPEC)

    def run_initial_and_additional_statsig_checks_9_total(self, mock_request):
        statsig.check_gate(self.statsig_user, "always_on_gate")
        statsig.get_config(self.statsig_user, "test_config")
        statsig.get_experiment(self.statsig_user, "sample_experiment")

        statsig.check_gate(self.statsig_user, "always_on_gate_sampled")
        statsig.get_config(self.statsig_user, "test_config_sampled")
        statsig.get_experiment(self.statsig_user, "not_started_exp")

        # the first set of events are not going to be sampled and avoid dedupe exposures
        statsig.check_gate(StatsigUser(generate_random_user_id()), "always_on_gate_sampled")
        statsig.get_config(StatsigUser(generate_random_user_id()), "test_config_sampled")
        statsig.get_experiment(StatsigUser(generate_random_user_id()), "not_started_exp")

    def test_apply_sampling_if_production(self, mock_request):
        options = StatsigOptions(
            api=_network_stub.host,
            tier=StatsigEnvironmentTier.production,
            disable_diagnostics=True)
        self.stub_network(mock_request, "on")
        statsig.initialize("secret-key", options=options)
        self.run_initial_and_additional_statsig_checks_9_total(mock_request)
        statsig.shutdown()

        not_sampled_event = self._events[0]
        self.assertEqual(not_sampled_event["statsigMetadata"].get("sampleRate"), None)
        self.assertEqual(not_sampled_event["statsigMetadata"].get("samplingMode"), 'on')
        self.assertEqual(6, len(self._events))  # 3 initial passes sampling events, 3 not sampled events

    def test_do_not_apply_sampling_if_development(self, mock_request):
        options = StatsigOptions(
            api=_network_stub.host,
            tier=StatsigEnvironmentTier.development,
            disable_diagnostics=True)
        self.stub_network(mock_request, "on")
        statsig.initialize("secret-key", options=options)
        self.run_initial_and_additional_statsig_checks_9_total(mock_request)
        statsig.shutdown()

        self.assertEqual(9, len(self._events))
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
        self.run_initial_and_additional_statsig_checks_9_total(mock_request)
        statsig.shutdown()

        self.assertEqual(9, len(self._events))
        not_sampled_event = self._events[0]
        self.assertEqual(not_sampled_event["statsigMetadata"].get("sampleRate"), None)
        self.assertEqual(not_sampled_event["statsigMetadata"]["samplingMode"], 'on')

    def test_apply_1_percent_sampling(self, mock_request):
        for attempt in range(3):  # Try up to 3 times
            self.__class__._events = []  # Reset the events for each attempt
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

            event_count = len(self._events)
            print(f"Attempt {attempt + 1}: Expecting around 100 events, received {event_count}")

            if 85 <= event_count <= 115:
                sampled_event = self._events[1]  # First event is not sampled
                if sampled_event["statsigMetadata"]["samplingRate"] == 101:
                    return

        self.fail("Sampling rate check failed in all 3 attempts.")

    def test_apply_10_percent_sampling(self, mock_request):
        for attempt in range(3):  # Try up to 3 times
            self.__class__._events = []  # Reset the events for each attempt
            options = StatsigOptions(
                api=_network_stub.host,
                tier=StatsigEnvironmentTier.production,
                disable_diagnostics=True
            )
            self.stub_network(mock_request, "on")
            statsig.initialize("secret-key", options=options)

            for i in range(10000):
                user = StatsigUser(generate_random_user_id())
                statsig.check_gate(user, "always_on_gate_sampled_10_percent")
            statsig.shutdown()

            event_count = len(self._events)
            print(f"Attempt {attempt + 1}: Expecting around 1000 events, received {event_count}")

            if 900 <= event_count <= 1100:
                sampled_event = self._events[1]  # First event is not sampled
                if sampled_event["statsigMetadata"]["samplingRate"] == 10:
                    return

        self.fail("Sampling rate check failed in all 3 attempts.")

    def test_apply_shadow_sampling_in_production_dropped(self, mock_request):
        options = StatsigOptions(
            api=_network_stub.host,
            tier=StatsigEnvironmentTier.production,
            disable_diagnostics=True)
        self.stub_network(mock_request, "shadow")
        statsig.initialize("secret-key", options=options)
        statsig.check_gate(self.statsig_user, "always_on_gate_sampled")  # the initial sample
        statsig.check_gate(StatsigUser(user_id="abc"), "always_on_gate_sampled")
        statsig.check_gate(self.statsig_user, "always_on_gate")

        statsig.shutdown()

        self.assertEqual(3, len(self._events))
        sampled_event = self._events[1]
        self.assertEqual(sampled_event["statsigMetadata"]["samplingRate"], 101)
        self.assertEqual(sampled_event["statsigMetadata"]["shadowLogged"], "dropped")
        self.assertEqual(sampled_event["statsigMetadata"]["samplingMode"], 'shadow')
        not_sampled_event = self._events[2]
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

        self.assertGreater(len(shadow_logged_events), 1)
        shadow_logged_event = shadow_logged_events[1]  # the first one is not sampled bc ttlset

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
        self.assertEqual(sampled_event["statsigMetadata"].get("sampleRate"), None)
        self.assertEqual(sampled_event["statsigMetadata"].get("shadowLogged"), None)
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

    def test_do_not_apply_sampling_to_all_exposure_forwarded_gate(self, mock_request):
        options = StatsigOptions(
            api=_network_stub.host,
            tier=StatsigEnvironmentTier.production,
            disable_diagnostics=True)
        self.stub_network(mock_request, "on")
        statsig.initialize("secret-key", options=options)
        user = StatsigUser(generate_random_user_id())
        statsig.check_gate(user, "forward_all_exposures_gate")
        statsig.shutdown()

        self.assertEqual(1, len(self._events))

    def test_sample_default_gates_when_no_exposure_forwarded(self, mock_request):
        options = StatsigOptions(
            api=_network_stub.host,
            tier=StatsigEnvironmentTier.production,
            disable_diagnostics=True)
        self.stub_network(mock_request, "on")
        statsig.initialize("secret-key", options=options)
        user = StatsigUser(generate_random_user_id())
        statsig.check_gate(user, "default_not_forward_all_exposures_gate")
        user = StatsigUser(generate_random_user_id())
        statsig.check_gate(user, "default_not_forward_all_exposures_gate")
        statsig.shutdown()

        self.assertEqual(1, len(self._events))

    def test_sample_non_allocated_layer(self, mock_request):
        options = StatsigOptions(
            api=_network_stub.host,
            tier=StatsigEnvironmentTier.production,
            disable_diagnostics=True)
        self.stub_network(mock_request, "on")
        statsig.initialize("secret-key", options=options)
        user = StatsigUser(generate_random_user_id())
        layer = statsig.get_layer(user, "not_allocated_layer")
        layer.get("param", "default")  # sampled by initial
        user = StatsigUser(generate_random_user_id())
        layer = statsig.get_layer(user, "not_allocated_layer")
        layer.get("param", "default")
        statsig.shutdown()

        self.assertEqual(1, len(self._events))
