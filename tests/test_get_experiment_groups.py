import copy
import json
import os
import unittest
from unittest.mock import patch

from network_stub import NetworkStub
from statsig import statsig, StatsigOptions, StatsigServer

with open(os.path.join(os.path.abspath(os.path.dirname(__file__)), '../testdata/download_config_specs.json')) as r:
    CONFIG_SPECS_RESPONSE = r.read()

_api_override = "http://get-experiment-groups-test"
_network_stub = NetworkStub(_api_override)

_options = StatsigOptions(api=_api_override, disable_diagnostics=True)

_NONE_RESULT = {"is_experiment_active": None, "groups": []}


def _make_specs_with_experiment(is_active=True):
    """
    Return a copy of the base config specs with sample_experiment patched to
    reflect what production specs look like:
      - isActive set as requested
      - experiment group rules have isExperimentGroup: True and idType: userID
      - the sizing/allocation rule (empty id) does NOT have isExperimentGroup set
    """
    specs = json.loads(CONFIG_SPECS_RESPONSE)
    for config in specs["dynamic_configs"]:
        if config["name"] == "sample_experiment":
            config["isActive"] = is_active
            for rule in config["rules"]:
                # Real group rules have a non-empty id and isExperimentGroup: True
                if rule.get("id"):
                    rule["isExperimentGroup"] = True
                    rule["idType"] = "userID"
            break
    return specs


def _setup_network_stub(specs=None):
    _network_stub.reset()
    _network_stub.stub_request_with_value(
        "download_config_specs/.*", 200,
        specs if specs is not None else json.loads(CONFIG_SPECS_RESPONSE)
    )
    _network_stub.stub_request_with_value("log_event", 202, {})


@patch('requests.Session.request', side_effect=_network_stub.mock)
class TestGetExperimentGroupsOnServer(unittest.TestCase):
    """Tests for StatsigServer.get_experiment_groups"""

    @patch('requests.Session.request', side_effect=_network_stub.mock)
    def setUp(self, mock_request):
        _setup_network_stub(_make_specs_with_experiment())
        self._server = StatsigServer()
        self._server.initialize("secret-key", _options)

    def tearDown(self):
        self._server.shutdown()

    def test_returns_active_state_and_groups_for_known_experiment(self, mock_request):
        result = self._server.get_experiment_groups("sample_experiment")

        self.assertIs(result["is_experiment_active"], True)
        self.assertGreater(len(result["groups"]), 0)

    def test_group_shape(self, mock_request):
        result = self._server.get_experiment_groups("sample_experiment")

        for group in result["groups"]:
            self.assertIn("group_name", group)
            self.assertIn("rule_id", group)
            self.assertIn("id_type", group)
            self.assertIn("return_value", group)

    def test_groups_match_spec(self, mock_request):
        result = self._server.get_experiment_groups("sample_experiment")

        groups_by_name = {g["group_name"]: g for g in result["groups"]}

        # Exactly the two variant groups — sizing rule must not appear
        self.assertEqual(sorted(groups_by_name), ["Control", "Test"])

        control = groups_by_name["Control"]
        self.assertEqual(control["rule_id"], "2RamGsERWbWMIMnSfOlQuX")
        self.assertEqual(control["id_type"], "userID")
        self.assertEqual(
            control["return_value"],
            {"experiment_param": "control", "layer_param": True, "second_layer_param": False},
        )

        test = groups_by_name["Test"]
        self.assertEqual(test["rule_id"], "2RamGujUou6h2bVNQWhtNZ")
        self.assertEqual(
            test["return_value"],
            {"experiment_param": "test", "layer_param": True, "second_layer_param": True},
        )

    def test_returns_none_result_for_unknown_experiment(self, mock_request):
        result = self._server.get_experiment_groups("nonexistent_experiment")

        self.assertEqual(result, _NONE_RESULT)

    def test_returns_none_result_for_dynamic_config(self, mock_request):
        # dynamic configs are not experiments; is_experiment_active should be None
        result = self._server.get_experiment_groups("test_config")

        self.assertEqual(result, _NONE_RESULT)

    def test_returns_none_result_for_empty_name(self, mock_request):
        result = self._server.get_experiment_groups("")

        self.assertEqual(result, _NONE_RESULT)

    def test_returns_none_result_for_autotune(self, mock_request):
        # Autotune configs live alongside experiments in dynamic_configs but have
        # a different entity; is_experiment_active should be None.
        specs = _make_specs_with_experiment()
        autotune = copy.deepcopy(
            next(c for c in specs["dynamic_configs"] if c["name"] == "test_config")
        )
        autotune["name"] = "test_autotune"
        autotune["entity"] = "autotune"
        specs["dynamic_configs"].append(autotune)
        _setup_network_stub(specs)

        server = StatsigServer()
        server.initialize("secret-key", _options)

        result = server.get_experiment_groups("test_autotune")
        self.assertEqual(result, _NONE_RESULT)

        server.shutdown()

    def test_returns_groups_for_inactive_experiment(self, mock_request):
        # A decided/inactive experiment still returns its groups along with the flag.
        _setup_network_stub(_make_specs_with_experiment(is_active=False))

        server = StatsigServer()
        server.initialize("secret-key", _options)

        result = server.get_experiment_groups("sample_experiment")
        self.assertIs(result["is_experiment_active"], False)
        group_names = sorted(g["group_name"] for g in result["groups"])
        self.assertEqual(group_names, ["Control", "Test"])

        server.shutdown()

    def test_active_state_false_when_is_active_unset(self, mock_request):
        # An experiment entity missing isActive reads as inactive, not unknown.
        specs = _make_specs_with_experiment()
        for config in specs["dynamic_configs"]:
            if config["name"] == "sample_experiment":
                del config["isActive"]
                break
        _setup_network_stub(specs)

        server = StatsigServer()
        server.initialize("secret-key", _options)

        result = server.get_experiment_groups("sample_experiment")
        self.assertIs(result["is_experiment_active"], False)
        self.assertGreater(len(result["groups"]), 0)

        server.shutdown()


@patch('requests.Session.request', side_effect=_network_stub.mock)
class TestGetExperimentGroupsModuleLevel(unittest.TestCase):
    """Tests for the module-level statsig.get_experiment_groups"""

    @classmethod
    @patch('requests.Session.request', side_effect=_network_stub.mock)
    def setUpClass(cls, mock_request):
        _setup_network_stub(_make_specs_with_experiment())
        statsig.initialize("secret-key", _options)

    @classmethod
    def tearDownClass(cls):
        statsig.shutdown()

    def test_module_level_returns_active_state_and_groups(self, mock_request):
        result = statsig.get_experiment_groups("sample_experiment")

        self.assertIs(result["is_experiment_active"], True)
        self.assertGreater(len(result["groups"]), 0)

    def test_module_level_group_shape(self, mock_request):
        result = statsig.get_experiment_groups("sample_experiment")

        for group in result["groups"]:
            self.assertIn("group_name", group)
            self.assertIn("rule_id", group)
            self.assertIn("id_type", group)
            self.assertIn("return_value", group)

    def test_module_level_returns_none_result_for_unknown(self, mock_request):
        result = statsig.get_experiment_groups("nonexistent_experiment")

        self.assertEqual(result, _NONE_RESULT)


if __name__ == '__main__':
    unittest.main()
