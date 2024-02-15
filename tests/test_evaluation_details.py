import json
import os
import unittest
from unittest.mock import patch

from statsig import StatsigOptions, StatsigServer, _Evaluator, StatsigUser, IDataStore
from statsig.evaluation_details import EvaluationReason
from gzip_helpers import GzipHelpers
from network_stub import NetworkStub

with open(os.path.join(os.path.abspath(os.path.dirname(__file__)), '../testdata/download_config_specs.json')) as r:
    CONFIG_SPECS_RESPONSE = r.read()

_api_override = "http://evaluation-details-test"
_network_stub = NetworkStub(_api_override)


@patch('time.time', return_value=123)
@patch('requests.request', side_effect=_network_stub.mock)
class TestEvaluationDetails(unittest.TestCase):
    _server: StatsigServer
    _evaluator: _Evaluator
    _user = StatsigUser(user_id="a-user")

    @patch('requests.request', side_effect=_network_stub.mock)
    def setUp(self, mock_request) -> None:
        server = StatsigServer()
        options = StatsigOptions(
            api=_api_override,
            disable_diagnostics=True
        )

        _network_stub.reset()
        self._events = []

        def on_log(url: str, **kwargs):
            self._events += GzipHelpers.decode_body(kwargs)["events"]

        _network_stub.stub_request_with_function("log_event", 202, on_log)

        _network_stub.stub_request_with_value(
            "download_config_specs/.*", 200, json.loads(CONFIG_SPECS_RESPONSE))

        server.initialize("secret-key", options)
        self._server = server
        self._evaluator = server._evaluator

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

    def test_uninitialized(self, mock_request, mock_time):
        self._evaluator._spec_store.init_reason = EvaluationReason.uninitialized

        self._server.check_gate(self._user, "always_on_gate")
        self._server.get_config(self._user, "test_config")
        self._server.get_experiment(self._user, "sample_experiment")
        layer = self._server.get_layer(self._user, "a_layer")
        layer.get("experiment_param", "fallback_value")

        self._server.shutdown()
        self.assertEqual(len(self._events), 3)
        self._assert_event_equal(self._events[0], {
            "eventName": "statsig::gate_exposure",
            "reason": "Uninitialized"
        }, True)
        self._assert_event_equal(self._events[1], {
            "eventName": "statsig::config_exposure",
            "reason": "Uninitialized",
        }, True)
        self._assert_event_equal(self._events[2], {
            "eventName": "statsig::config_exposure",
            "reason": "Uninitialized"
        }, True)

    def test_unrecognized(self, mock_request, mock_time):
        self._server.check_gate(self._user, "not_a_gate")
        self._server.get_config(self._user, "not_a_config")
        self._server.get_experiment(self._user, "not_an_experiment")
        layer = self._server.get_layer(self._user, "not_a_layer")
        layer.get("a_value", "fallback_value")

        self._server.shutdown()
        self.assertEqual(len(self._events), 3)
        self._assert_event_equal(self._events[0], {
            "eventName": "statsig::gate_exposure",
            "reason": "Unrecognized"
        })
        self._assert_event_equal(self._events[1], {
            "eventName": "statsig::config_exposure",
            "reason": "Unrecognized",
        })
        self._assert_event_equal(self._events[2], {
            "eventName": "statsig::config_exposure",
            "reason": "Unrecognized"
        })

    def test_network(self, mock_request, mock_time):
        self._server.check_gate(self._user, "always_on_gate")
        self._server.get_config(self._user, "test_config")
        self._server.get_experiment(self._user, "sample_experiment")
        layer = self._server.get_layer(self._user, "a_layer")
        layer.get("experiment_param", "fallback_value")

        self._server.shutdown()
        self.assertEqual(len(self._events), 4)
        self._assert_event_equal(self._events[0], {
            "eventName": "statsig::gate_exposure",
            "reason": "Network"
        })
        self._assert_event_equal(self._events[1], {
            "eventName": "statsig::config_exposure",
            "reason": "Network",
        })
        self._assert_event_equal(self._events[2], {
            "eventName": "statsig::config_exposure",
            "reason": "Network"
        })

    def test_local_override(self, mock_request, mock_time):
        self._server.override_gate("always_on_gate", False)
        self._server.override_config("sample_experiment", {})

        self._server.check_gate(self._user, "always_on_gate")
        self._server.get_config(self._user, "sample_experiment")

        self._server.shutdown()
        self.assertEqual(len(self._events), 2)
        self._assert_event_equal(self._events[0], {
            "eventName": "statsig::gate_exposure",
            "reason": "LocalOverride"
        })
        self._assert_event_equal(self._events[1], {
            "eventName": "statsig::config_exposure",
            "reason": "LocalOverride",
        })

    def test_bootstrap(self, mock_request, mock_time):
        opts = StatsigOptions(
            bootstrap_values=CONFIG_SPECS_RESPONSE, api=_api_override, disable_diagnostics=True)
        bootstrap_server = StatsigServer()
        bootstrap_server.initialize('secret-key', opts)

        bootstrap_server.check_gate(self._user, "always_on_gate")
        bootstrap_server.get_config(self._user, "test_config")
        bootstrap_server.get_experiment(self._user, "sample_experiment")
        layer = bootstrap_server.get_layer(self._user, "a_layer")
        layer.get("experiment_param", "fallback_value")

        bootstrap_server.shutdown()
        self.assertEqual(len(self._events), 4)
        self._assert_event_equal(self._events[0], {
            "eventName": "statsig::gate_exposure",
            "reason": "Bootstrap"
        })
        self._assert_event_equal(self._events[1], {
            "eventName": "statsig::config_exposure",
            "reason": "Bootstrap",
        })
        self._assert_event_equal(self._events[2], {
            "eventName": "statsig::config_exposure",
            "reason": "Bootstrap"
        })
        self._assert_event_equal(self._events[3], {
            "eventName": "statsig::layer_exposure",
            "reason": "Bootstrap"
        })

    def test_data_store(self, mock_request, mock_time):
        class _TestAdapter(IDataStore):
            def get(self, key: str):
                return CONFIG_SPECS_RESPONSE

        opts = StatsigOptions(data_store=_TestAdapter(), api=_api_override, disable_diagnostics=True)
        data_store_server = StatsigServer()
        data_store_server.initialize('secret-key', opts)

        data_store_server.check_gate(self._user, "always_on_gate")
        data_store_server.get_config(self._user, "test_config")
        data_store_server.get_experiment(self._user, "sample_experiment")
        layer = data_store_server.get_layer(self._user, "a_layer")
        layer.get("experiment_param", "fallback_value")

        data_store_server.shutdown()
        self.assertEqual(len(self._events), 4)
        self._assert_event_equal(self._events[0], {
            "eventName": "statsig::gate_exposure",
            "reason": "DataAdapter"
        })
        self._assert_event_equal(self._events[1], {
            "eventName": "statsig::config_exposure",
            "reason": "DataAdapter",
        })
        self._assert_event_equal(self._events[2], {
            "eventName": "statsig::config_exposure",
            "reason": "DataAdapter"
        })
        self._assert_event_equal(self._events[3], {
            "eventName": "statsig::layer_exposure",
            "reason": "DataAdapter"
        })

    def test_logging(self, mock_request, mock_time):
        self._server.check_gate(self._user, "always_on_gate")
        self._server.get_config(self._user, "test_config")
        self._server.get_experiment(self._user, "sample_experiment")
        layer = self._server.get_layer(self._user, "a_layer")
        layer.get("experiment_param", "fallback_value")
        self._server.shutdown()

        self.assertEqual(len(self._events), 4)


if __name__ == '__main__':
    unittest.main()
