import json
import os
import unittest
from unittest.mock import patch

from statsig import StatsigOptions, StatsigServer, _Evaluator, StatsigUser, IDataStore
from network_stub import NetworkStub

with open(os.path.join(os.path.abspath(os.path.dirname(__file__)), '../testdata/download_config_specs.json')) as r:
    CONFIG_SPECS_RESPONSE = r.read()

_api_override = "http://evaluation-details-test"
_network_stub = NetworkStub(_api_override)


@patch('time.time', return_value=123)
@patch('requests.post', side_effect=_network_stub.mock)
class TestInitDiagnostics(unittest.TestCase):
    _server: StatsigServer
    _evaluator: _Evaluator
    _user = StatsigUser(user_id="a-user")

    @patch('requests.post', side_effect=_network_stub.mock)
    def setUp(self, mock_post) -> None:
        self._server = StatsigServer()
        self._options = StatsigOptions(
            api=_api_override,
        )

        _network_stub.reset()
        self._events = []

        def on_log(url: str, data: dict):
            self._events += data["json"]["events"]

        _network_stub.stub_request_with_function("log_event", 202, on_log)

        _network_stub.stub_request_with_value(
            "download_config_specs", 200, json.loads(CONFIG_SPECS_RESPONSE))

        self.get_id_list_response = {}

        _network_stub.stub_request_with_value(
            "get_id_lists", 200, {})

        def assert_event_equal(event: dict, values: dict,
                               skip_sync_times: bool = False):
            self.assertEqual(event["eventName"], values["eventName"])
            self.assertEqual(event["metadata"]["reason"], values["reason"])
            self.assertEqual(event["metadata"]["serverTime"], 123 * 1000)

            if not skip_sync_times:
                self.assertEqual(event["metadata"]
                                 ["configSyncTime"], 1631638014811)
                self.assertEqual(event["metadata"]["initTime"], 1631638014811)
            else:
                self.assertEqual(event["metadata"]["configSyncTime"], 0)
                self.assertEqual(event["metadata"]["initTime"], 0)

        self._assert_event_equal = assert_event_equal

        def assert_marker_equal(
                marker: any,
                key,
                action=None,
                step=None,
                value=None,
        ):
            self.assertEqual(key, marker['key'])
            self.assertEqual(action, marker['action'])
            self.assertEqual(step, marker['step'])
            self.assertEqual(value, marker['value'])
            self.assertIsInstance(marker['timestamp'], int)

        self._assert_marker_equal = assert_marker_equal

    def test_init_success(self, mock_post, mock_time):
        self._server.initialize("secret-key", self._options)
        self._server.shutdown()
        self.assertEqual(len(self._events), 1)

        event = self._events[0]
        self.assertEqual(event['eventName'], 'statsig::diagnostics')

        metadata = event["metadata"]
        self.assertEqual(metadata['context'], 'initialize')

        markers = metadata["markers"]
        self._assert_marker_equal(markers[0], "overall", "start")
        self._assert_marker_equal(
          markers[1],
          'download_config_specs',
          'start',
          'network_request',
        )
        self._assert_marker_equal(
            markers[2],
            'download_config_specs',
            'end',
            'network_request',
            200,
        )
        self._assert_marker_equal(markers[3], 'download_config_specs', 'start', 'process')
        self._assert_marker_equal(
            markers[4],
            'download_config_specs',
            'end',
            'process',
            True,
        )
        self._assert_marker_equal(markers[5], 'get_id_lists', 'start', 'network_request')
        self._assert_marker_equal(
            markers[6],
            'get_id_lists',
            'end',
            'network_request',
            200,
        )
        # self._assert_marker_equal(markers[7], 'get_id_lists', 'start', 'process', 0)
        # self._assert_marker_equal(markers[8], 'get_id_lists', 'end', 'process', True) don't run if id_list is empty
        self._assert_marker_equal(markers[7], 'overall', 'end')
        self.assertEqual(len(markers), 8)

    def test_init_failure(self, mock_post, mock_time):
        _network_stub.stub_request_with_value(
            "download_config_specs", 500, "{}")

        self._server.initialize("secret-key", self._options)
        self._server.shutdown()
        self.assertEqual(len(self._events), 1)

        event = self._events[0]
        self.assertEqual(event['eventName'], 'statsig::diagnostics')

        metadata = event["metadata"]
        self.assertEqual(metadata['context'], 'initialize')

        markers = metadata["markers"]
        self._assert_marker_equal(markers[0], "overall", "start")
        self._assert_marker_equal(
          markers[1],
          'download_config_specs',
          'start',
          'network_request',
        )
        self._assert_marker_equal(
            markers[2],
            'download_config_specs',
            'end',
            'network_request',
            500,
        )
        self._assert_marker_equal(
            markers[3],
            'download_config_specs',
            'start',
            'network_request',
        )
        self._assert_marker_equal(
            markers[4],
            'download_config_specs',
            'end',
            'network_request',
            500
        )
        self._assert_marker_equal(markers[5], 'get_id_lists', 'start', 'network_request')
        self._assert_marker_equal(
            markers[6],
            'get_id_lists',
            'end',
            'network_request',
            200,
        )
        self._assert_marker_equal(markers[7], 'overall', 'end')
        self.assertEqual(len(markers), 8)

    def test_init_get_id_list(self, mock_post, mock_time):
        _network_stub.stub_request_with_value("get_id_lists", 200, {"list_1": {
            "name": "list_1",
            "size": 10,
            "url": _network_stub.host + "/list_1",
            "creationTime": 1,
            "fileID": "file_id_1",
        }})

        self._server.initialize("secret-key", self._options)
        self._server.shutdown()
        self.assertEqual(len(self._events), 1)

        event = self._events[0]
        self.assertEqual(event['eventName'], 'statsig::diagnostics')

        metadata = event["metadata"]
        self.assertEqual(metadata['context'], 'initialize')

        markers = metadata["markers"]
        self._assert_marker_equal(markers[0], "overall", "start")
        self._assert_marker_equal(
          markers[1],
          'download_config_specs',
          'start',
          'network_request',
        )
        self._assert_marker_equal(
            markers[2],
            'download_config_specs',
            'end',
            'network_request',
            200,
        )
        self._assert_marker_equal(markers[3], 'download_config_specs', 'start', 'process')
        self._assert_marker_equal(
            markers[4],
            'download_config_specs',
            'end',
            'process',
            True,
        )
        self._assert_marker_equal(markers[5], 'get_id_lists', 'start', 'network_request')
        self._assert_marker_equal(
            markers[6],
            'get_id_lists',
            'end',
            'network_request',
            200,
        )
        self._assert_marker_equal(markers[7], 'get_id_lists', 'start', 'process')
        self._assert_marker_equal(markers[8], 'get_id_lists', 'end', 'process', True)
        self._assert_marker_equal(markers[9], 'overall', 'end')
        self.assertEqual(len(markers), 10)

    def test_init_bootstrap(self, mock_post, mock_time):

        self._server.initialize("secret-key", StatsigOptions(
            api=_api_override,
            bootstrap_values=CONFIG_SPECS_RESPONSE
        ))
        self._server.shutdown()
        self.assertEqual(len(self._events), 1)

        event = self._events[0]
        self.assertEqual(event['eventName'], 'statsig::diagnostics')

        metadata = event["metadata"]
        self.assertEqual(metadata['context'], 'initialize')

        markers = metadata["markers"]
        self._assert_marker_equal(markers[0], "overall", "start")
        self._assert_marker_equal(
          markers[1],
          'bootstrap',
          'start',
          'load',
        )
        self._assert_marker_equal(
            markers[2],
            'bootstrap',
            'end',
            'load',
        )
        # Skip download_config / get_id_list
        self._assert_marker_equal(markers[5], 'overall', 'end')
        self.assertEqual(len(markers), 6)

    def test_init_data_adapter(self, mock_post, mock_time):

        class _TestAdapter(IDataStore):
            def get(self, key: str):
                return CONFIG_SPECS_RESPONSE

        self._server.initialize("secret-key", StatsigOptions(
            api=_api_override,
            data_store=_TestAdapter()
        ))
        self._server.shutdown()
        self.assertEqual(len(self._events), 1)

        event = self._events[0]
        self.assertEqual(event['eventName'], 'statsig::diagnostics')

        metadata = event["metadata"]
        self.assertEqual(metadata['context'], 'initialize')

        markers = metadata["markers"]
        self._assert_marker_equal(markers[0], "overall", "start")
        self._assert_marker_equal(
          markers[1],
          'bootstrap',
          'start',
          'load',
        )
        self._assert_marker_equal(
            markers[2],
            'bootstrap',
            'end',
            'load',
        )
        self._assert_marker_equal(markers[3], 'get_id_lists', 'start', 'network_request')
        self._assert_marker_equal(
            markers[4],
            'get_id_lists',
            'end',
            'network_request',
            200,
        )
        self._assert_marker_equal(markers[5], 'overall', 'end')
        self.assertEqual(len(markers), 6)


if __name__ == '__main__':
    unittest.main()
