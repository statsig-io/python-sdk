import time
import os
import unittest
import json

from unittest.mock import patch
from gzip_helpers import GzipHelpers
from network_stub import NetworkStub
from statsig import statsig, StatsigUser, StatsigOptions, StatsigEvent, StatsigEnvironmentTier
from statsig.evaluation_details import EvaluationReason

with open(os.path.join(os.path.abspath(os.path.dirname(__file__)), '../testdata/download_config_specs.json')) as r:
    CONFIG_SPECS_RESPONSE = r.read()
PARSED_CONFIG_SPEC = json.loads(CONFIG_SPECS_RESPONSE)

_network_stub = NetworkStub("http://test-statsig-e2e")


@patch('requests.request', side_effect=_network_stub.mock)
class TestStatsigE2E(unittest.TestCase):
    _logs = {}

    @classmethod
    @patch('requests.request', side_effect=_network_stub.mock)
    def setUpClass(cls, mock_request):
        _network_stub.stub_request_with_value(
            "download_config_specs/.*", 200, PARSED_CONFIG_SPEC)
        _network_stub.stub_request_with_value("list_1", 200, "+7/rrkvF6\n")
        _network_stub.stub_request_with_value("get_id_lists", 200, {"list_1": {
            "name": "list_1",
            "size": 10,
            "url": _network_stub.host + "/list_1",
            "creationTime": 1,
            "fileID": "file_id_1",
        }})

        def log_event_callback(url: str, **kwargs):
            cls._logs = GzipHelpers.decode_body(kwargs)

        _network_stub.stub_request_with_function(
            "log_event", 202, log_event_callback)

        cls.statsig_user = StatsigUser(
            "regular_user_id", email="testuser@statsig.com", private_attributes={"test": 123})
        cls.random_user = StatsigUser("random")
        cls._logs = {}
        options = StatsigOptions(
            api=_network_stub.host,
            tier=StatsigEnvironmentTier.development,
            disable_diagnostics=True)

        statsig.initialize("secret-key", options)
        cls.initTime = round(time.time() * 1000)

    @classmethod
    def tearDownClass(cls) -> None:
        statsig.shutdown()

    # hacky, yet effective. python runs tests in alphabetical order.
    def test_a_check_gate(self, mock_request):
        self.assertEqual(
            statsig.check_gate(self.statsig_user, "always_on_gate"),
            True
        )
        self.assertIsNone(self.statsig_user._statsig_environment)
        self.assertEqual(
            statsig.check_gate(self.statsig_user, "on_for_statsig_email"),
            True
        )
        self.assertEqual(
            statsig.check_gate(self.random_user, "on_for_statsig_email"),
            False
        )
        self.assertIsNone(self.random_user._statsig_environment)

    def test_a_get_feature_gate(self, mock_request):
        gate = statsig.get_feature_gate(self.statsig_user, "always_on_gate")
        self.assertEqual(gate.get_value(), True)
        self.assertEqual(gate.get_name(), "always_on_gate")
        self.assertEqual(gate.get_evaluation_details().reason, EvaluationReason.network)
        self.assertEqual(gate.get_evaluation_details().config_sync_time, PARSED_CONFIG_SPEC['time'])

    def test_b_dynamic_config(self, mock_request):
        config = statsig.get_config(self.statsig_user, "test_config")
        self.assertEqual(
            config.get_value(),
            dict(
                number=7,
                string="statsig",
                boolean=False,
            )
        )
        self.assertEqual(config.group_name, "statsig email")
        self.assertEqual(config.get_evaluation_details().reason, EvaluationReason.network)
        self.assertEqual(config.get_evaluation_details().config_sync_time, PARSED_CONFIG_SPEC['time'])
        config = statsig.get_config(self.random_user, "test_config")
        self.assertEqual(
            config.get_value(),
            dict(
                number=4,
                string="default",
                boolean=True,
            )
        )
        self.assertIsNone(config.group_name)
        self.assertEqual(config.get_evaluation_details().reason, EvaluationReason.network)
        self.assertEqual(config.get_evaluation_details().config_sync_time, PARSED_CONFIG_SPEC['time'])

    def test_c_experiment(self, mock_request):
        config = statsig.get_experiment(self.statsig_user, "sample_experiment")
        self.assertEqual(
            config.get_value(),
            dict(
                experiment_param="test",
                layer_param=True,
                second_layer_param=True
            )
        )
        config = statsig.get_experiment(self.random_user, "sample_experiment")
        self.assertEqual(
            config.get_value(),
            dict(
                experiment_param="control",
                layer_param=True,
                second_layer_param=False
            )
        )

    def test_d_log_event(self, mock_request):
        event = StatsigEvent(self.statsig_user, "purchase", value="SKU_12345", metadata=dict(
            price="9.99", item_name="diet_coke_48_pack"))
        statsig.log_event(event)
        self.assertEqual(len([]), 0)

    def test_e_evaluate_all(self, mock_request):
        self.assertEqual(statsig.evaluate_all(self.statsig_user),
                         {
                             "feature_gates": {
                                 "always_on_gate": {
                                     "value": True,
                                     "rule_id": "6N6Z8ODekNYZ7F8gFdoLP5"
                                 },
                                 "on_for_statsig_email": {
                                     "value": True,
                                     "rule_id": "7w9rbTSffLT89pxqpyhuqK"
                                 },
                                 "on_for_id_list": {
                                     "value": True,
                                     "rule_id": "7w9rbTSffLT89pxqpyhuqA"
                                 }
                             },
                             "dynamic_configs": {
                                 "test_config": {
                                     "value": {
                                         "boolean": False,
                                         "number": 7,
                                         "string": "statsig"
                                     },
                                     "rule_id": "1kNmlB23wylPFZi1M0Divl"
                                 },
                                 "sample_experiment": {
                                     "value": {
                                         "experiment_param": "test",
                                         "layer_param": True,
                                         "second_layer_param": True
                                     },
                                     "rule_id": "2RamGujUou6h2bVNQWhtNZ"
                                 }
                             }
        }
        )

    # test_z ensures this runs last
    def test_z_logs(self, mock_request):
        statsig.shutdown()
        events = self._logs["events"]
        self.assertEqual(len(events), 8)
        self.assertEqual(events[0]["eventName"], "statsig::gate_exposure")
        self.assertEqual(events[0]["metadata"]["gate"], "always_on_gate")
        self.assertEqual(events[0]["metadata"]["gateValue"], "true")
        self.assertEqual(events[0]["metadata"]["ruleID"],
                         "6N6Z8ODekNYZ7F8gFdoLP5")
        self.assertEqual(events[0]["user"].get(
            "privateAttributes", None), None)
        self.assertEqual(events[0]["user"].get(
            "statsigEnvironment", None), {"tier": "development"})
        self.assertAlmostEqual(events[0]["time"], self.initTime, delta=60000)

        self.assertEqual(events[1]["eventName"], "statsig::gate_exposure")
        self.assertEqual(events[1]["metadata"]["gate"], "on_for_statsig_email")
        self.assertEqual(events[1]["metadata"]["gateValue"], "true")
        self.assertEqual(events[1]["metadata"]["ruleID"],
                         "7w9rbTSffLT89pxqpyhuqK")
        self.assertEqual(events[1]["user"].get(
            "privateAttributes", None), None)
        self.assertEqual(events[1]["user"].get(
            "statsigEnvironment", None), {"tier": "development"})
        self.assertAlmostEqual(events[1]["time"], self.initTime, delta=60000)

        self.assertEqual(events[2]["eventName"], "statsig::gate_exposure")
        self.assertEqual(events[2]["metadata"]["gate"], "on_for_statsig_email")
        self.assertEqual(events[2]["metadata"]["gateValue"], "false")
        self.assertEqual(events[2]["metadata"]["ruleID"], "default")
        self.assertEqual(events[2]["user"].get(
            "privateAttributes", None), None)
        self.assertEqual(events[2]["user"].get(
            "statsigEnvironment", None), {"tier": "development"})
        self.assertAlmostEqual(events[2]["time"], self.initTime, delta=60000)

        self.assertEqual(events[3]["eventName"], "statsig::config_exposure")
        self.assertEqual(events[3]["metadata"]["config"], "test_config")
        self.assertEqual(events[3]["metadata"]["ruleID"],
                         "1kNmlB23wylPFZi1M0Divl")
        self.assertEqual(events[3]["user"].get(
            "privateAttributes", None), None)
        self.assertEqual(events[3]["user"].get(
            "statsigEnvironment", None), {"tier": "development"})
        self.assertAlmostEqual(events[3]["time"], self.initTime, delta=60000)

        self.assertEqual(events[4]["eventName"], "statsig::config_exposure")
        self.assertEqual(events[4]["metadata"]["config"], "test_config")
        self.assertEqual(events[4]["metadata"]["ruleID"], "default")
        self.assertEqual(events[4]["user"].get(
            "privateAttributes", None), None)
        self.assertEqual(events[4]["user"].get(
            "statsigEnvironment", None), {"tier": "development"})
        self.assertAlmostEqual(events[4]["time"], self.initTime, delta=60000)

        self.assertEqual(events[5]["eventName"], "statsig::config_exposure")
        self.assertEqual(events[5]["metadata"]["config"], "sample_experiment")
        self.assertEqual(events[5]["metadata"]["ruleID"],
                         "2RamGujUou6h2bVNQWhtNZ")
        self.assertEqual(events[5]["user"].get(
            "privateAttributes", None), None)
        self.assertEqual(events[5]["user"].get(
            "statsigEnvironment", None), {"tier": "development"})
        self.assertAlmostEqual(events[5]["time"], self.initTime, delta=60000)

        self.assertEqual(events[6]["eventName"], "statsig::config_exposure")
        self.assertEqual(events[6]["metadata"]["config"], "sample_experiment")
        self.assertEqual(events[6]["metadata"]["ruleID"],
                         "2RamGsERWbWMIMnSfOlQuX")
        self.assertEqual(events[6]["user"].get(
            "privateAttributes", None), None)
        self.assertEqual(events[6]["user"].get(
            "statsigEnvironment", None), {"tier": "development"})
        self.assertAlmostEqual(events[6]["time"], self.initTime, delta=60000)

        self.assertEqual(events[7]["eventName"], "purchase")
        self.assertEqual(events[7]["value"], "SKU_12345")
        self.assertEqual(events[7]["metadata"]
                         ["item_name"], "diet_coke_48_pack")
        self.assertEqual(events[7]["metadata"]["price"], "9.99")
        self.assertEqual(events[7]["user"]["userID"], "regular_user_id")
        self.assertEqual(events[7]["user"]["email"], "testuser@statsig.com")
        self.assertEqual(events[7]["user"].get(
            "privateAttributes", None), None)
        self.assertEqual(events[7]["user"].get(
            "statsigEnvironment", None), {"tier": "development"})
        self.assertAlmostEqual(events[7]["time"], self.initTime, delta=60000)

        self.assertEqual(self._logs["statsigMetadata"]["sdkType"], "py-server")


if __name__ == '__main__':
    unittest.main()
