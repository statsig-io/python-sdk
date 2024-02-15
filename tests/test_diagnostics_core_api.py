import json
import os
import unittest
from unittest.mock import patch

from statsig import StatsigOptions, StatsigServer, _Evaluator, StatsigUser, IDataStore
from gzip_helpers import GzipHelpers
from network_stub import NetworkStub
from statsig.diagnostics import SamplingRate

with open(
    os.path.join(
        os.path.abspath(os.path.dirname(__file__)),
        "../testdata/download_config_specs.json",
    )
) as r:
    CONFIG_SPECS_RESPONSE = r.read()

_api_override = "http://evaluation-details-test"
_network_stub = NetworkStub(_api_override)


@patch("time.time", return_value=123)
@patch("requests.request", side_effect=_network_stub.mock)
class TestDiagnosticsCoreAPI(unittest.TestCase):
    _server: StatsigServer
    _evaluator: _Evaluator
    _user = StatsigUser(user_id="a-user")

    @patch("requests.request", side_effect=_network_stub.mock)
    def setUp(self, mock_request) -> None:
        response = json.loads(CONFIG_SPECS_RESPONSE)
        response["diagnostics"] = {
            SamplingRate.DCS.value: 100,
            SamplingRate.ID_LIST.value: 100,
            SamplingRate.INITIALIZE.value: 10000,
            SamplingRate.LOG_EVENT.value: 100,
            SamplingRate.API_CALL.value: 10000,
        }
        self._server = StatsigServer()
        self._options = StatsigOptions(
            api=_api_override,
        )

        _network_stub.reset()
        self._events = []

        def on_log(url: str, **kwargs):
            self._events += GzipHelpers.decode_body(kwargs, False)["events"]

        _network_stub.stub_request_with_function("log_event", 202, on_log)

        _network_stub.stub_request_with_value("download_config_specs/.*", 200, response)

        self.get_id_list_response = {}

        _network_stub.stub_request_with_value("get_id_lists", 200, {})

        def assert_marker_equal(
            marker: dict,
            key,
            action=None,
            step=None,
            tags={},
        ):
            # Verify basic fields
            self.assertEqual(key, marker.get("key"))
            self.assertEqual(action, marker.get("action"))
            self.assertEqual(step, marker.get("step"))

            # Verify tags
            for tag_key, tag_value in tags.items():
                assert tag_key in marker, f"Tag '{tag_key}' does not exist in marker"
                assert (
                    marker[tag_key] == tag_value
                ), f"Tag '{tag_key}' value mismatch in marker"

        self._assert_marker_equal = assert_marker_equal

    def test_api_call(self, mock_request, mock_time):
        user = StatsigUser(user_id="user_id")
        self._server.initialize("secret-key", self._options)
        self._server.check_gate(user, "always_on_gate")
        self._server.get_config(user, "test_config")
        self._server.get_experiment(user, "sample_experiment")
        self._server.get_layer(user, "a_layer")
        self._server.shutdown()
        core_api_event = next(
            event
            for event in self._events
            if event["eventName"] == "statsig::diagnostics"
            and event["metadata"]["context"] == "api_call"
        )
        markers = core_api_event["metadata"]["markers"]
        self.assertTrue("statsigOptions" not in core_api_event["metadata"])
        self._assert_marker_equal(
            markers[0],
            "check_gate",
            "start",
            None,
            {"configName": "always_on_gate", "markerID": "check_gate_0"},
        )
        self._assert_marker_equal(
            markers[1],
            "check_gate",
            "end",
            None,
            {"success": True, "markerID": "check_gate_0"},
        )
        self._assert_marker_equal(
            markers[2],
            "get_config",
            "start",
            None,
            {"configName": "test_config", "markerID": "get_config_2"},
        )
        self._assert_marker_equal(
            markers[3],
            "get_config",
            "end",
            None,
            {"markerID": "get_config_2", "success": True},
        )
        self._assert_marker_equal(
            markers[4],
            "get_experiment",
            "start",
            None,
            {
                "markerID": "get_experiment_4",
                "configName": "sample_experiment",
            },
        )
        self._assert_marker_equal(
            markers[5],
            "get_experiment",
            "end",
            None,
            {
                "markerID": "get_experiment_4",
                "success": True,
            },
        )
        self._assert_marker_equal(
            markers[6],
            "get_layer",
            "start",
            None,
            {
                "markerID": "get_layer_6",
                "configName": "a_layer",
            },
        )
        self._assert_marker_equal(
            markers[7],
            "get_layer",
            "end",
            None,
            {
                "markerID": "get_layer_6",
                "success": True,
            },
        )

    def test_disable_diagnostics(self, mock_request, mock_time):
        user = StatsigUser(user_id="user_id")
        self._options.disable_diagnostics = True
        self._server.initialize("secret-key", self._options)
        self._server.check_gate(user, "always_on_gate")
        self._server.get_config(user, "test_config")
        self._server.shutdown()
        core_api_events = [
            event
            for event in self._events
            if event["eventName"] == "statsig::diagnostics"
            and event["metadata"]["context"] == "api_call"
        ]
        self.assertEqual(len(core_api_events), 0)

if __name__ == "__main__":
    unittest.main()
