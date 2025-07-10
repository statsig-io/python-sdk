import json
import os
import unittest
from typing import List, Optional
from unittest.mock import patch

from statsig import statsig, StatsigOptions, StatsigUser
from tests.network_stub import NetworkStub

_network_stub = NetworkStub("http://test-optional-callbacks")

with open(os.path.join(os.path.abspath(os.path.dirname(__file__)), '../testdata/download_config_specs.json')) as r:
    CONFIG_SPECS_RESPONSE = r.read()


@patch('requests.Session.request', side_effect=_network_stub.mock)
class TestOptionalCallbacks(unittest.TestCase):
    @classmethod
    @patch('requests.Session.request', side_effect=_network_stub.mock)
    def setUpClass(cls, mock_request) -> None:
        cls._events = []
        cls._event_flush_detail = {
            "success": False,
            "error": None,
            "status_code": None
        }
        _network_stub.stub_request_with_value(
            "download_config_specs/.*", 200, json.loads(CONFIG_SPECS_RESPONSE))

    def setUp(self, ):
        self.__class__._events = []
        self.__class__._event_flush_detail = {
            "success": False,
            "error": None,
            "status_code": None
        }

    def events_flushed_callback(self, success: bool, events: List[dict], status_code: Optional[int],
                                error: Optional[Exception]):
        self._events += events
        self._event_flush_detail["success"] = success
        self._event_flush_detail["error"] = error
        self._event_flush_detail["status_code"] = status_code

    def test_events_flushed_callback_success(self, network_mock):
        _network_stub.stub_request_with_value("log_event", 202, {})
        options = StatsigOptions(
            api=_network_stub.host,
            events_flushed_callback=self.events_flushed_callback
        )
        statsig.initialize("secret-key", options)
        statsig.check_gate(StatsigUser("test_user"), "always_on_gate")
        statsig.shutdown()

        self.assertEqual(len(self._events), 2)
        self.assertEqual(self._events[0]["eventName"], "statsig::diagnostics")
        self.assertEqual(self._events[1]["eventName"], "statsig::gate_exposure")
        self.assertEqual(self._events[1]["metadata"]["gate"], "always_on_gate")
        self.assertEqual(self._event_flush_detail["success"], True)
        self.assertIsNone(self._event_flush_detail["error"])
        self.assertEqual(self._event_flush_detail["status_code"], 202)

    def test_events_flushed_callback_failure(self, network_mock):
        _network_stub.stub_request_with_value("log_event", 500, {})
        options = StatsigOptions(
            api=_network_stub.host,
            events_flushed_callback=self.events_flushed_callback
        )
        statsig.initialize("secret-key", options)
        statsig.check_gate(StatsigUser("test_user"), "always_on_gate")
        statsig.shutdown()

        self.assertEqual(len(self._events), 2)
        self.assertEqual(self._events[0]["eventName"], "statsig::diagnostics")
        self.assertEqual(self._events[1]["eventName"], "statsig::gate_exposure")
        self.assertEqual(self._events[1]["metadata"]["gate"], "always_on_gate")
        self.assertEqual(self._event_flush_detail["success"], False)
        self.assertIsNotNone(self._event_flush_detail["error"])
        self.assertEqual(self._event_flush_detail["status_code"], 500)
