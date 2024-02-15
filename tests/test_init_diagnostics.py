import json
import os
import unittest
from unittest.mock import patch

from statsig import StatsigOptions, StatsigServer, _Evaluator, StatsigUser, IDataStore
from gzip_helpers import GzipHelpers
from network_stub import NetworkStub

with open(
    os.path.join(
        os.path.abspath(os.path.dirname(__file__)),
        "../testdata/download_config_specs.json",
    )
) as r:
    CONFIG_SPECS_RESPONSE = r.read()

_api_override = "http://evaluation-details-test"
_network_stub = NetworkStub(_api_override)


@patch('time.time', return_value=123)
@patch('requests.request', side_effect=_network_stub.mock)
class TestDiagnostics(unittest.TestCase):
    _server: StatsigServer
    _evaluator: _Evaluator
    _user = StatsigUser(user_id="a-user")

    @patch('requests.request', side_effect=_network_stub.mock)
    def setUp(self, mock_request) -> None:
        self._server = StatsigServer()
        self._options = StatsigOptions(
            api=_api_override,
        )

        _network_stub.reset()
        self._events = []

        def on_log(url: str, **kwargs):
            self._events += GzipHelpers.decode_body(kwargs, False)["events"]

        _network_stub.stub_request_with_function("log_event", 202, on_log)

        _network_stub.stub_request_with_value(
            "download_config_specs/.*", 200, json.loads(CONFIG_SPECS_RESPONSE)
        )

        self.get_id_list_response = {}

        _network_stub.stub_request_with_value("get_id_lists", 200, {})

        def assert_event_equal(
            event: dict, values: dict, skip_sync_times: bool = False
        ):
            self.assertEqual(event["eventName"], values["eventName"])
            self.assertEqual(event["metadata"]["reason"], values["reason"])
            self.assertEqual(event["metadata"]["serverTime"], 123 * 1000)

            if not skip_sync_times:
                self.assertEqual(event["metadata"]["configSyncTime"], 1631638014811)
                self.assertEqual(event["metadata"]["initTime"], 1631638014811)
            else:
                self.assertEqual(event["metadata"]["configSyncTime"], 0)
                self.assertEqual(event["metadata"]["initTime"], 0)

        self._assert_event_equal = assert_event_equal

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

    def test_init_success(self, mock_request, mock_time):
        self._server.initialize("secret-key", self._options)
        self._server.shutdown()
        self.assertEqual(len(self._events), 1)

        event = self._events[0]
        self.assertEqual(event["eventName"], "statsig::diagnostics")

        metadata = event["metadata"]
        self.assertEqual(metadata["context"], "initialize")
        self.assertEqual(metadata["statsigOptions"], self._options.logging_copy)
        markers = metadata["markers"]
        self._assert_marker_equal(markers[0], "overall", "start")
        self._assert_marker_equal(
            markers[1],
            "download_config_specs",
            "start",
            "network_request",
        )
        self._assert_marker_equal(
            markers[2],
            "download_config_specs",
            "end",
            "network_request",
            {"statusCode": 200},
        )
        self._assert_marker_equal(
            markers[3], "download_config_specs", "start", "process"
        )
        self._assert_marker_equal(
            markers[4],
            "download_config_specs",
            "end",
            "process",
            {"success": True},
        )
        self._assert_marker_equal(
            markers[5], "get_id_list_sources", "start", "network_request"
        )
        self._assert_marker_equal(
            markers[6],
            "get_id_list_sources",
            "end",
            "network_request",
            {"statusCode": 200},
        )
        self._assert_marker_equal(markers[7], "get_id_list_sources", "start", "process")
        self._assert_marker_equal(
            markers[8],
            "get_id_list_sources",
            "end",
            "process",
            {"success": True},
        )
        self._assert_marker_equal(markers[9], "overall", "end", None, {"success": True})
        self.assertEqual(len(markers), 10)

    def test_init_failure(self, mock_request, mock_time):
        _network_stub.stub_request_with_value("download_config_specs/.*", 500, "{}")

        self._server.initialize("secret-key", self._options)
        self._server.shutdown()
        self.assertEqual(len(self._events), 1)

        event = self._events[0]
        self.assertEqual(event["eventName"], "statsig::diagnostics")

        metadata = event["metadata"]
        self.assertEqual(metadata["context"], "initialize")

        markers = metadata["markers"]
        self._assert_marker_equal(markers[0], "overall", "start")
        self._assert_marker_equal(
            markers[1],
            "download_config_specs",
            "start",
            "network_request",
        )
        self._assert_marker_equal(
            markers[2],
            "download_config_specs",
            "end",
            "network_request",
            {"statusCode": 500},
        )
        self._assert_marker_equal(
            markers[3], "get_id_list_sources", "start", "network_request"
        )
        self._assert_marker_equal(
            markers[4],
            "get_id_list_sources",
            "end",
            "network_request",
            {"statusCode": 200},
        )
        self._assert_marker_equal(markers[5], "get_id_list_sources", "start", "process")
        self._assert_marker_equal(
            markers[6],
            "get_id_list_sources",
            "end",
            "process",
            {"success": True},
        )
        self._assert_marker_equal(markers[7], "overall", "end", None, {"success": True})
        self.assertEqual(len(markers), 8)

    def test_init_get_id_list(self, mock_request, mock_time):
        _network_stub.stub_request_with_value(
            "get_id_list_sources",
            200,
            {
                "list_1": {
                    "name": "list_1",
                    "size": 10,
                    "url": _network_stub.host + "/list_1",
                    "creationTime": 1,
                    "fileID": "file_id_1",
                }
            },
        )

        self._server.initialize("secret-key", self._options)
        self._server.shutdown()
        self.assertEqual(len(self._events), 1)

        event = self._events[0]
        self.assertEqual(event["eventName"], "statsig::diagnostics")

        metadata = event["metadata"]
        self.assertEqual(metadata["context"], "initialize")

        markers = metadata["markers"]
        self._assert_marker_equal(markers[0], "overall", "start")
        self._assert_marker_equal(
            markers[1],
            "download_config_specs",
            "start",
            "network_request",
        )
        self._assert_marker_equal(
            markers[2],
            "download_config_specs",
            "end",
            "network_request",
            {"statusCode": 200},
        )
        self._assert_marker_equal(
            markers[3], "download_config_specs", "start", "process"
        )
        self._assert_marker_equal(
            markers[4],
            "download_config_specs",
            "end",
            "process",
            {"success": True},
        )
        self._assert_marker_equal(
            markers[5], "get_id_list_sources", "start", "network_request"
        )
        self._assert_marker_equal(
            markers[6],
            "get_id_list_sources",
            "end",
            "network_request",
            {"statusCode": 200},
        )
        self._assert_marker_equal(markers[7], "get_id_list_sources", "start", "process")
        self._assert_marker_equal(
            markers[8], "get_id_list_sources", "end", "process", {"success": True}
        )
        self._assert_marker_equal(markers[9], "overall", "end")
        self.assertEqual(len(markers), 10)

    def test_init_bootstrap(self, mock_request, mock_time):
        self._server.initialize(
            "secret-key",
            StatsigOptions(api=_api_override, bootstrap_values=CONFIG_SPECS_RESPONSE),
        )
        self._server.shutdown()
        self.assertEqual(len(self._events), 1)

        event = self._events[0]
        self.assertEqual(event["eventName"], "statsig::diagnostics")

        metadata = event["metadata"]
        self.assertEqual(metadata["context"], "initialize")

        markers = metadata["markers"]
        self._assert_marker_equal(markers[0], "overall", "start")
        self._assert_marker_equal(
            markers[1],
            "bootstrap",
            "start",
            "process",
        )
        self._assert_marker_equal(
            markers[2],
            "bootstrap",
            "end",
            "process",
        )
        # Skip download_config / get_id_list
        self._assert_marker_equal(markers[7], "overall", "end")
        self.assertEqual(len(markers), 8)


if __name__ == "__main__":
    unittest.main()
