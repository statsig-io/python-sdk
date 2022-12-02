import os
import json
from unittest.mock import patch

from tests.network_stub import NetworkStub
from statsig import statsig, StatsigUser, StatsigOptions, StatsigEnvironmentTier, Layer
from tests.test_case_with_extras import TestCaseWithExtras

with open(os.path.join(os.path.abspath(os.path.dirname(__file__)),
                       '../testdata/download_config_specs.json')) as r:
    CONFIG_SPECS_RESPONSE = r.read()

_network_stub = NetworkStub("http://test-manual-exposures")


@patch('requests.post', side_effect=_network_stub.mock)
class TestManualExposures(TestCaseWithExtras):
    _user = StatsigUser("dloomb")
    _logs = {}

    @classmethod
    def setUpClass(cls):
        _network_stub.reset()
        _network_stub.stub_request_with_value(
            "download_config_specs", 200, json.loads(CONFIG_SPECS_RESPONSE))

        def log_event_callback(url: str, data: dict):
            cls._logs = data["json"]

        _network_stub.stub_request_with_function(
            "log_event", 202, log_event_callback)

        cls.options = StatsigOptions(
            api=_network_stub.host,
            tier=StatsigEnvironmentTier.development)

    def test_api_with_exposure_logging_disabled(self, mock_post):
        self._start()
        statsig.check_gate_with_exposure_logging_disabled(self._user, 'always_on_gate')
        statsig.get_config_with_exposure_logging_disabled(self._user, 'test_config')
        statsig.get_experiment_with_exposure_logging_disabled(self._user, 'sample_experiment')
        layer = statsig.get_layer_with_exposure_logging_disabled(self._user, 'a_layer')
        layer.get('experiment_param')
        statsig.shutdown()

        events = TestManualExposures._logs["events"]
        self.assertEqual(len(events), 0)

    def test_manual_exposure_logging(self, mock_post):
        self._start()
        statsig.manually_log_gate_exposure(self._user, 'always_on_gate')
        statsig.manually_log_config_exposure(self._user, 'test_config')
        statsig.manually_log_experiment_exposure(self._user, 'sample_experiment')
        statsig.manually_log_layer_parameter_exposure(self._user, 'a_layer', 'experiment_param')
        statsig.shutdown()

        events = TestManualExposures._logs["events"]
        self.assertEqual(len(events), 4)

        gate_exposure = events[0]
        self.assertEqual(gate_exposure.get('eventName', ''), 'statsig::gate_exposure')
        self.assertEqual(gate_exposure.get('metadata', {}).get('gate', ''), 'always_on_gate')
        self.assertEqual(gate_exposure.get('metadata', {}).get('isManualExposure', ''), 'true')
        config_exposure = events[1]
        self.assertEqual(config_exposure.get('eventName', ''), 'statsig::config_exposure')
        self.assertEqual(config_exposure.get('metadata', {}).get('config', ''), 'test_config')
        self.assertEqual(config_exposure.get('metadata', {}).get('isManualExposure', ''), 'true')
        experiment_exposure = events[2]
        self.assertEqual(experiment_exposure.get('eventName', ''), 'statsig::config_exposure')
        self.assertEqual(experiment_exposure.get('metadata', {}).get('config', ''), 'sample_experiment')
        self.assertEqual(experiment_exposure.get('metadata', {}).get('isManualExposure', ''), 'true')
        layer_exposure = events[3]
        self.assertEqual(layer_exposure.get('eventName', ''), 'statsig::layer_exposure')
        self.assertEqual(layer_exposure.get('metadata', {}).get('config', ''), 'a_layer')
        self.assertEqual(layer_exposure.get('metadata', {}).get('isManualExposure', ''), 'true')

    def _start(self):
        TestManualExposures._logs = {'events': []}
        statsig.initialize("secret-key", self.options)
