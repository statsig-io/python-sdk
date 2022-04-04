import time
import os
import unittest
import json
from .mockserver import MockServer

from statsig import statsig, StatsigUser, StatsigOptions, StatsigEvent, StatsigEnvironmentTier

with open(os.path.join(os.path.abspath(os.path.dirname(__file__)), '../testdata/download_config_specs.json')) as r:
    CONFIG_SPECS_RESPONSE = r.read()


class TestStatsigE2E(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.server = MockServer(port=1234)
        cls.server.start()
        cls.server.add_json_response(
            "/download_config_specs", json.loads(CONFIG_SPECS_RESPONSE))
        cls.server.add_json_response(
            "/get_id_lists", json.loads("{}"))
        cls.server.add_log_event_response(
            cls.check_logs.__get__(cls, cls.__class__))
        cls.statsig_user = StatsigUser(
            "123", email="testuser@statsig.com", private_attributes={"test": 123})
        cls.random_user = StatsigUser("random")
        cls.logs = {}
        options = StatsigOptions(
            api=cls.server.url, tier=StatsigEnvironmentTier.development)

        statsig.initialize("secret-key", options)
        cls.initTime = round(time.time() * 1000)

    def check_logs(self, json):
        self.logs = json

    # hacky, yet effective. python runs tests in alphabetical order.
    def test_a_check_gate(self):
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

    def test_b_dynamic_config(self):
        config = statsig.get_config(self.statsig_user, "test_config")
        self.assertEqual(
            config.get_value(),
            dict(
                number=7,
                string="statsig",
                boolean=False,
            )
        )
        config = statsig.get_config(self.random_user, "test_config")
        self.assertEqual(
            config.get_value(),
            dict(
                number=4,
                string="default",
                boolean=True,
            )
        )

    def test_c_experiment(self):
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

    def test_d_log_event(self):
        event = StatsigEvent(self.statsig_user, "purchase", value="SKU_12345", metadata=dict(
            price="9.99", item_name="diet_coke_48_pack"))
        statsig.log_event(event)
        self.assertEqual(len([]), 0)

    def test_e_evaluate_all(self):
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
    def test_z_logs(self):
        statsig.shutdown()
        events = self.logs["events"]
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
        self.assertEqual(events[7]["user"]["userID"], "123")
        self.assertEqual(events[7]["user"]["email"], "testuser@statsig.com")
        self.assertEqual(events[7]["user"].get(
            "privateAttributes", None), None)
        self.assertEqual(events[7]["user"].get(
            "statsigEnvironment", None), {"tier": "development"})
        self.assertAlmostEqual(events[7]["time"], self.initTime, delta=60000)

        self.assertEqual(self.logs["statsigMetadata"]["sdkType"], "py-server")

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown_server()


if __name__ == '__main__':
    unittest.main()
