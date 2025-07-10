import copy
import json
import os
import time
import unittest
from collections import defaultdict
from datetime import datetime
from typing import Optional, Any, Dict
from unittest.mock import patch

from build.lib.statsig import StatsigUser
from statsig import statsig, StatsigOptions
from statsig.evaluation_details import DataSource
from statsig.interface_observability_client import ObservabilityClient
from tests.network_stub import NetworkStub

_network_stub = NetworkStub("http://test-telemetry-logger")

with open(os.path.join(os.path.abspath(os.path.dirname(__file__)), '../testdata/download_config_specs.json')) as r:
    CONFIG_SPECS_RESPONSE = r.read()
PARSED_CONFIG_SPEC = json.loads(CONFIG_SPECS_RESPONSE)


class MockObservabilityClient(ObservabilityClient):
    def __init__(self):
        self._logs = defaultdict(list)
        self.initialized = False

    def init(self) -> None:
        self.initialized = True

    def increment(self, metric_name: str, value: int = 1, tags: Optional[Dict[str, Any]] = None) -> None:
        if self.initialized:
            self._logs['increment'].append((metric_name, value, tags))

    def gauge(self, metric_name: str, value: float, tags: Optional[Dict[str, Any]] = None) -> None:
        if self.initialized:
            self._logs['gauge'].append((metric_name, value, tags))

    def distribution(self, metric_name: str, value: float, tags: Optional[Dict[str, Any]] = None) -> None:
        if self.initialized:
            self._logs['distribution'].append((metric_name, value, tags))

    def should_enable_high_cardinality_for_this_tag(self, tag: str) -> bool:
        if self.initialized:
            return True


class AlwaysThrowObClient(ObservabilityClient):
    def init(self) -> None:
        raise Exception("Always throw")

    def increment(self, metric_name: str, value: int = 1, tags: Optional[Dict[str, Any]] = None) -> None:
        raise Exception("Always throw")

    def gauge(self, metric_name: str, value: float, tags: Optional[Dict[str, Any]] = None) -> None:
        raise Exception("Always throw")

    def distribution(self, metric_name: str, value: float, tags: Optional[Dict[str, Any]] = None) -> None:
        raise Exception("Always throw")


@patch('requests.Session.request', side_effect=_network_stub.mock)
class TestTelemetryLogger(unittest.TestCase):
    @classmethod
    @patch('requests.Session.request', side_effect=_network_stub.mock)
    def setUp(cls, mock_request):
        _network_stub.reset()

        def dcs_callback(url: str, **kwargs):
            time.sleep(0.2)
            return PARSED_CONFIG_SPEC

        _network_stub.stub_request_with_function(
            "download_config_specs/.*", 200, dcs_callback)

    def tearDown(self):
        statsig.shutdown()

    def test_initialize(self, mock_request):
        ob_client = MockObservabilityClient()
        options = StatsigOptions(api=_network_stub.host, observability_client=ob_client)
        statsig.initialize("secret-key", options)
        self.assertEqual(len(ob_client._logs['distribution']), 1)
        self.assertEqual(ob_client._logs['distribution'][0][0], "statsig.sdk.initialization")

    def test_initialize_timeout(self, mock_request):
        ob_client = MockObservabilityClient()
        options = StatsigOptions(api=_network_stub.host, init_timeout=0.1, observability_client=ob_client)
        statsig.initialize("secret-key", options)
        self.assertEqual(len(ob_client._logs['distribution']), 1)
        self.assertEqual(ob_client._logs['distribution'][0][0], "statsig.sdk.initialization")

    def test_no_update_counter(self, mock_request):
        _network_stub.stub_request_with_value(
            "download_config_specs/.*", 200, {"has_updates": False})
        ob_client = MockObservabilityClient()
        options = StatsigOptions(api=_network_stub.host, observability_client=ob_client, rulesets_sync_interval=0.5)
        statsig.initialize("secret-key", options)
        self.assertEqual(len(ob_client._logs['distribution']), 1)
        self.assertEqual(ob_client._logs['distribution'][0][0], "statsig.sdk.initialization")
        time.sleep(0.7)
        self.assertEqual(len(ob_client._logs['increment']), 1)
        self.assertEqual(ob_client._logs['increment'][0][0], "statsig.sdk.config_no_update")

    def test_high_card_tags_logged(self, mock_request):
        ob_client = MockObservabilityClient()
        options = StatsigOptions(api=_network_stub.host, observability_client=ob_client, rulesets_sync_interval=1)
        statsig.initialize("secret-key", options)
        self.assertEqual(len(ob_client._logs['distribution']), 1)
        new_config_spec = copy.deepcopy(PARSED_CONFIG_SPEC)
        if "time" in new_config_spec:
            new_config_spec["time"] += 1
        _network_stub.stub_request_with_value(
            "download_config_specs/.*", 200, new_config_spec)
        time.sleep(1.1)
        self.assertEqual(len(ob_client._logs['distribution']), 2)
        self.assertEqual(ob_client._logs['distribution'][1][0], "statsig.sdk.config_propagation_diff")
        self.assertIn('lcut', ob_client._logs['distribution'][1][2])
        self.assertIn('prev_lcut', ob_client._logs['distribution'][1][2])

    def test_ob_client_throw_exception(self, mock_request):
        ob_client = AlwaysThrowObClient()
        options = StatsigOptions(api=_network_stub.host, observability_client=ob_client)
        init_details = statsig.initialize("secret-key", options)
        self.assertEqual(init_details.init_success, True)
        self.assertEqual(init_details.store_populated, True)
        self.assertEqual(init_details.source, DataSource.NETWORK)
        gate = statsig.check_gate(StatsigUser("test_user"), "always_on_gate")
        self.assertTrue(gate)

    def test_log_sdk_exception_counter(self, mock_request):
        ob_client = MockObservabilityClient()
        options = StatsigOptions(api=_network_stub.host, observability_client=ob_client)
        statsig.initialize("secret-key", options)
        statsig.check_gate(StatsigUser(user_id="123", custom={"time": datetime.now()}), "always_on_gate")
        statsig.flush()
        self.assertEqual(len(ob_client._logs['increment']), 1)
        self.assertEqual(ob_client._logs['increment'][0][0], "statsig.sdk.sdk_exceptions_count")

    def test_error_callback(self, mock_request):
        def error_callback(tag: str, exception: Exception):
            self.assertEqual(tag, "statsig::log_event_failed")
            self.assertIsInstance(exception, Exception)

        options = StatsigOptions(api=_network_stub.host, sdk_error_callback=error_callback)
        statsig.initialize("secret-key", options)
        statsig.check_gate(StatsigUser(user_id="123", custom={"time": datetime.now()}), "always_on_gate")
        statsig.flush()

    def test_always_throw_error_callback(self, mock_request):
        def error_callback(tag: str, exception: Exception):
            raise Exception("Always throw")

        options = StatsigOptions(api=_network_stub.host, sdk_error_callback=error_callback)
        init_details = statsig.initialize("secret-key", options)
        self.assertEqual(init_details.init_success, True)
        self.assertEqual(init_details.store_populated, True)
        self.assertEqual(init_details.source, DataSource.NETWORK)
        gate = statsig.check_gate(StatsigUser("test_user"), "always_on_gate")
        self.assertTrue(gate)

    def test_events_successfully_sent_count(self, mock_request):
        _network_stub.stub_request_with_value(
            "log_event", 200, {})
        ob_client = MockObservabilityClient()
        options = StatsigOptions(api=_network_stub.host, observability_client=ob_client)
        statsig.initialize("secret-key", options)
        statsig.check_gate(StatsigUser(user_id="123"), "always_on_gate")
        statsig.flush()
        self.assertEqual(len(ob_client._logs['increment']), 1)
        self.assertEqual(ob_client._logs['increment'][0][0], "statsig.sdk.events_successfully_sent_count")
        self.assertEqual(ob_client._logs['increment'][0][1], 2)  # diagnostic event + gate check
