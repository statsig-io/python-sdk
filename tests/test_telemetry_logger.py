import copy
import json
import os
import time
import unittest
from collections import defaultdict
from datetime import datetime
from typing import Optional, Any, Dict
from unittest.mock import patch

from statsig import statsig, StatsigOptions, StatsigUser
from statsig import globals
from statsig.evaluation_details import DataSource
from statsig.interface_observability_client import ObservabilityClient
from statsig.statsig_telemetry_logger import SyncContext
from tests.network_stub import NetworkStub

_network_stub = NetworkStub("http://test-telemetry-logger")

with open(
    os.path.join(
        os.path.abspath(os.path.dirname(__file__)),
        "../testdata/download_config_specs.json",
    )
) as r:
    CONFIG_SPECS_RESPONSE = r.read()
PARSED_CONFIG_SPEC = json.loads(CONFIG_SPECS_RESPONSE)


class MockObservabilityClient(ObservabilityClient):
    def __init__(self):
        self._logs = defaultdict(list)
        self.initialized = False

    def init(self) -> None:
        self.initialized = True

    def increment(
        self, metric_name: str, value: int = 1, tags: Optional[Dict[str, Any]] = None
    ) -> None:
        if self.initialized:
            self._logs["increment"].append((metric_name, value, tags))

    def gauge(
        self, metric_name: str, value: float, tags: Optional[Dict[str, Any]] = None
    ) -> None:
        if self.initialized:
            self._logs["gauge"].append((metric_name, value, tags))

    def distribution(
        self, metric_name: str, value: float, tags: Optional[Dict[str, Any]] = None
    ) -> None:
        if self.initialized:
            self._logs["distribution"].append((metric_name, value, tags))

    def should_enable_high_cardinality_for_this_tag(self, tag: str) -> bool:
        if self.initialized:
            return True


class AlwaysThrowObClient(ObservabilityClient):
    def init(self) -> None:
        raise Exception("Always throw")

    def increment(
        self, metric_name: str, value: int = 1, tags: Optional[Dict[str, Any]] = None
    ) -> None:
        raise Exception("Always throw")

    def gauge(
        self, metric_name: str, value: float, tags: Optional[Dict[str, Any]] = None
    ) -> None:
        raise Exception("Always throw")

    def distribution(
        self, metric_name: str, value: float, tags: Optional[Dict[str, Any]] = None
    ) -> None:
        raise Exception("Always throw")


@patch("requests.Session.request", side_effect=_network_stub.mock)
class TestTelemetryLogger(unittest.TestCase):
    @classmethod
    @patch("requests.Session.request", side_effect=_network_stub.mock)
    def setUp(cls, mock_request):
        _network_stub.reset()

        def dcs_callback(url: str, **kwargs):
            time.sleep(0.2)
            return PARSED_CONFIG_SPEC

        _network_stub.stub_request_with_function(
            "download_config_specs/.*", 200, dcs_callback
        )

    def tearDown(self):
        statsig.shutdown()

    @staticmethod
    def _metric_logs(logs, metric_name: str):
        return [log for log in logs if log[0] == metric_name]

    def test_initialize(self, mock_request):
        ob_client = MockObservabilityClient()
        options = StatsigOptions(api=_network_stub.host, observability_client=ob_client)
        statsig.initialize("secret-key", options)
        self.assertEqual(len(ob_client._logs["distribution"]), 1)
        self.assertEqual(
            ob_client._logs["distribution"][0][0], "statsig.sdk.initialization"
        )

    def test_initialize_timeout(self, mock_request):
        ob_client = MockObservabilityClient()
        options = StatsigOptions(
            api=_network_stub.host, init_timeout=0.1, observability_client=ob_client
        )
        statsig.initialize("secret-key", options)
        self.assertEqual(len(ob_client._logs["distribution"]), 1)
        self.assertEqual(
            ob_client._logs["distribution"][0][0], "statsig.sdk.initialization"
        )

    def test_no_update_counter(self, mock_request):
        _network_stub.stub_request_with_value(
            "download_config_specs/.*", 200, {"has_updates": False}
        )
        ob_client = MockObservabilityClient()
        options = StatsigOptions(
            api=_network_stub.host,
            observability_client=ob_client,
            rulesets_sync_interval=0.5,
        )
        statsig.initialize("secret-key", options)
        self.assertEqual(len(ob_client._logs["distribution"]), 1)
        self.assertEqual(
            ob_client._logs["distribution"][0][0], "statsig.sdk.initialization"
        )
        time.sleep(0.7)
        config_no_update_logs = self._metric_logs(
            ob_client._logs["increment"], "statsig.sdk.config_no_update"
        )
        self.assertEqual(len(config_no_update_logs), 1)

    def test_high_card_tags_logged(self, mock_request):
        ob_client = MockObservabilityClient()
        options = StatsigOptions(
            api=_network_stub.host,
            observability_client=ob_client,
            rulesets_sync_interval=1,
        )
        statsig.initialize("secret-key", options)
        self.assertEqual(len(ob_client._logs["distribution"]), 1)
        new_config_spec = copy.deepcopy(PARSED_CONFIG_SPEC)
        if "time" in new_config_spec:
            new_config_spec["time"] += 1
        _network_stub.stub_request_with_value(
            "download_config_specs/.*", 200, new_config_spec
        )
        time.sleep(1.1)
        self.assertEqual(len(ob_client._logs["distribution"]), 3)
        self.assertEqual(
            ob_client._logs["distribution"][1][0], "statsig.sdk.config_propagation_diff"
        )
        self.assertIn("lcut", ob_client._logs["distribution"][1][2])
        self.assertIn("prev_lcut", ob_client._logs["distribution"][1][2])

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
        statsig.check_gate(
            StatsigUser(user_id="123", custom={"time": datetime.now()}),
            "always_on_gate",
        )
        statsig.flush()
        sdk_exception_logs = self._metric_logs(
            ob_client._logs["increment"], "statsig.sdk.sdk_exceptions_count"
        )
        self.assertEqual(len(sdk_exception_logs), 1)

    def test_error_callback(self, mock_request):
        def error_callback(tag: str, exception: Exception):
            self.assertEqual(tag, "statsig::log_event_failed")
            self.assertIsInstance(exception, Exception)

        options = StatsigOptions(
            api=_network_stub.host, sdk_error_callback=error_callback
        )
        statsig.initialize("secret-key", options)
        statsig.check_gate(
            StatsigUser(user_id="123", custom={"time": datetime.now()}),
            "always_on_gate",
        )
        statsig.flush()

    def test_always_throw_error_callback(self, mock_request):
        def error_callback(tag: str, exception: Exception):
            raise Exception("Always throw")

        options = StatsigOptions(
            api=_network_stub.host, sdk_error_callback=error_callback
        )
        init_details = statsig.initialize("secret-key", options)
        self.assertEqual(init_details.init_success, True)
        self.assertEqual(init_details.store_populated, True)
        self.assertEqual(init_details.source, DataSource.NETWORK)
        gate = statsig.check_gate(StatsigUser("test_user"), "always_on_gate")
        self.assertTrue(gate)

    def test_network_request_errors_do_not_trigger_error_callback(self, mock_request):
        def broken_dcs_callback(url: str, **kwargs):
            raise ConnectionError("network down")

        _network_stub.stub_request_with_function(
            "download_config_specs/.*", 200, broken_dcs_callback
        )

        callback_tags = []

        def error_callback(tag: str, exception: Exception):
            callback_tags.append(tag)

        options = StatsigOptions(
            api=_network_stub.host, sdk_error_callback=error_callback, init_timeout=0.1
        )
        statsig.initialize("secret-key", options)

        self.assertEqual(callback_tags, [])

    def test_events_successfully_sent_count(self, mock_request):
        _network_stub.stub_request_with_value("log_event", 200, {})
        ob_client = MockObservabilityClient()
        options = StatsigOptions(api=_network_stub.host, observability_client=ob_client)
        statsig.initialize("secret-key", options)
        statsig.check_gate(StatsigUser(user_id="123"), "always_on_gate")
        statsig.flush()
        event_logs = self._metric_logs(
            ob_client._logs["increment"], "statsig.sdk.events_successfully_sent_count"
        )
        self.assertEqual(len(event_logs), 1)
        self.assertEqual(event_logs[0][1], 2)  # diagnostic event + gate check

    def test_get_id_lists_and_id_list_download_metrics(self, mock_request):
        _network_stub.stub_request_with_value(
            "get_id_lists",
            200,
            {
                "list_1": {
                    "name": "list_1",
                    "size": 3,
                    "url": _network_stub.host + "/list_1",
                    "creationTime": 1,
                    "fileID": "file_id_1",
                },
                "list_2": {
                    "name": "list_2",
                    "size": 3,
                    "url": _network_stub.host + "/list_2",
                    "creationTime": 1,
                    "fileID": "file_id_2",
                },
            },
        )
        _network_stub.stub_request_with_value("list_1", 200, "+1\r")
        _network_stub.stub_request_with_value("list_2", 200, "+2\r")

        ob_client = MockObservabilityClient()
        options = StatsigOptions(api=_network_stub.host, observability_client=ob_client)
        statsig.initialize("secret-key", options)

        id_list_download_logs = self._metric_logs(
            ob_client._logs["increment"], "statsig.sdk.id_list_download"
        )
        self.assertEqual(len(id_list_download_logs), 1)
        self.assertEqual(id_list_download_logs[0][1], 2)
        self.assertTrue(id_list_download_logs[0][2]["success"])
        self.assertEqual(id_list_download_logs[0][2]["source_api"], "http://test-telemetry-logger/")


    def test_get_id_lists_metric_failure(self, mock_request):
        _network_stub.stub_request_with_value("get_id_lists", 500, {})

        ob_client = MockObservabilityClient()
        options = StatsigOptions(api=_network_stub.host, observability_client=ob_client)
        statsig.initialize("secret-key", options)
        id_list_download_logs = self._metric_logs(
            ob_client._logs["increment"], "statsig.sdk.id_list_download"
        )
        self.assertEqual(len(id_list_download_logs), 0)

    def test_id_list_download_failure_metrics(self, mock_request):
        _network_stub.stub_request_with_value(
            "get_id_lists",
            200,
            {
                "bad_list": {
                    "name": "bad_list",
                    "size": 3,
                    "url": _network_stub.host + "/bad_list",
                    "creationTime": 1,
                    "fileID": "file_id_bad",
                },
            },
        )
        _network_stub.stub_request_with_value("bad_list", 500, {})

        ob_client = MockObservabilityClient()
        options = StatsigOptions(api=_network_stub.host, observability_client=ob_client)
        statsig.initialize("secret-key", options)

        id_list_download_logs = self._metric_logs(
            ob_client._logs["increment"], "statsig.sdk.id_list_download"
        )
        self.assertEqual(len(id_list_download_logs), 1)
        self.assertEqual(id_list_download_logs[0][1], 1)
        self.assertFalse(id_list_download_logs[0][2]["success"])
        self.assertEqual(id_list_download_logs[0][2]["source_api"], "http://test-telemetry-logger/")

    def test_background_sync_count_metrics(self, mock_request):
        ob_client = MockObservabilityClient()
        options = StatsigOptions(api=_network_stub.host, observability_client=ob_client)
        statsig.initialize("secret-key", options)
        ob_client._logs["distribution"].clear()

        globals.logger.log_sync_attempt(SyncContext.DCS, "Network", True, "http://test", 123.0)
        globals.logger.log_sync_attempt(
            SyncContext.ID_LISTS, "StatsigNetwork", False, "http://test", 456.0
        )

        attempt_logs = self._metric_logs(
            ob_client._logs["distribution"], "statsig.sdk.background_sync_duration_ms"
        )
        self.assertEqual(len(attempt_logs), 2)
        attempt_logs_by_context = {log[2]["context"]: log for log in attempt_logs}
        self.assertEqual(attempt_logs_by_context["dcs"][1], 123.0)
        self.assertEqual(attempt_logs_by_context["dcs"][2]["source"], "Network")
        self.assertTrue(attempt_logs_by_context["dcs"][2]["success"])
        self.assertFalse(attempt_logs_by_context["dcs"][2]["fallback_used"])
        self.assertEqual(attempt_logs_by_context["id_lists"][1], 456.0)
        self.assertEqual(attempt_logs_by_context["id_lists"][2]["source"], "StatsigNetwork")
        self.assertFalse(attempt_logs_by_context["id_lists"][2]["success"])
        self.assertTrue(attempt_logs_by_context["id_lists"][2]["fallback_used"])

    def test_initialize_does_not_emit_background_sync_metrics(self, mock_request):
        ob_client = MockObservabilityClient()
        options = StatsigOptions(api=_network_stub.host, observability_client=ob_client)
        statsig.initialize("secret-key", options)

        attempt_logs = self._metric_logs(
            ob_client._logs["distribution"], "statsig.sdk.background_sync_duration_ms"
        )
        self.assertEqual(len(attempt_logs), 0)
