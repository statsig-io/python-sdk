import os
import json
from unittest.mock import patch

from typing import Optional
from gzip_helpers import GzipHelpers
from network_stub import NetworkStub
from statsig import statsig, StatsigUser, StatsigOptions, StatsigEnvironmentTier, Layer
from test_case_with_extras import TestCaseWithExtras

with open(os.path.join(os.path.abspath(os.path.dirname(__file__)),
                       '../testdata/download_config_specs.json')) as r:
    CONFIG_SPECS_RESPONSE = r.read()

_network_stub = NetworkStub("http://test-manual-exposures")


@patch('requests.request', side_effect=_network_stub.mock)
class TestManualExposures(TestCaseWithExtras):
    _user = StatsigUser("dloomb")
    _logs = {}

    @classmethod
    def setUpClass(cls):
        _network_stub.reset()
        _network_stub.stub_request_with_value(
            "download_config_specs/.*", 200, json.loads(CONFIG_SPECS_RESPONSE))

        def log_event_callback(url: str, **kwargs):
            cls._logs = GzipHelpers.decode_body(kwargs)

        _network_stub.stub_request_with_function(
            "log_event", 202, log_event_callback)

        cls.options = StatsigOptions(
            api=_network_stub.host,
            tier=StatsigEnvironmentTier.development,
            disable_diagnostics=True
        )

    def setUp(self):
        TestManualExposures._logs = {'events': []}
        statsig.initialize("secret-key", self.options)

    def tearDown(self) -> None:
        statsig.shutdown()

    def test_api_with_exposure_logging_disabled(self, mock_request):
        statsig.check_gate_with_exposure_logging_disabled(self._user, 'always_on_gate')
        statsig.get_config_with_exposure_logging_disabled(self._user, 'test_config')
        statsig.get_experiment_with_exposure_logging_disabled(self._user, 'sample_experiment')
        layer = statsig.get_layer_with_exposure_logging_disabled(self._user, 'a_layer')
        layer.get('experiment_param')
        statsig.shutdown()

        events = TestManualExposures._logs["events"]
        self.assertEqual(len(events), 0)

    def test_manual_exposure_logging(self, mock_request):
        statsig.manually_log_gate_exposure(self._user, 'always_on_gate')
        statsig.manually_log_config_exposure(self._user, 'test_config')
        statsig.manually_log_experiment_exposure(self._user, 'sample_experiment')
        statsig.manually_log_layer_parameter_exposure(self._user, 'a_layer', 'experiment_param')
        statsig.shutdown()

        events = TestManualExposures._logs["events"]
        self.assertEqual(len(events), 4)

        gate_exposure = events[0]
        self._assert_exposure_event_name(gate_exposure, 'statsig::gate_exposure')
        self._assert_exposure_metadata(
            gate_exposure, gate='always_on_gate', is_manual_exposure='true')
        config_exposure = events[1]
        self._assert_exposure_event_name(config_exposure, 'statsig::config_exposure')
        self._assert_exposure_metadata(
            config_exposure, config='test_config', is_manual_exposure='true')
        experiment_exposure = events[2]
        self._assert_exposure_event_name(experiment_exposure, 'statsig::config_exposure')
        self._assert_exposure_metadata(
            experiment_exposure, config='sample_experiment', is_manual_exposure='true')
        layer_exposure = events[3]
        self._assert_exposure_event_name(layer_exposure, 'statsig::layer_exposure')
        self._assert_exposure_metadata(layer_exposure, config='a_layer', is_manual_exposure='true')

    def _assert_exposure_event_name(self, exposure: object, event_name: str):
        self.assertEqual(exposure.get('eventName', ''), event_name)

    def _assert_exposure_metadata(
            self,
            exposure: object,
            gate: Optional[str] = None,
            config: Optional[str] = None,
            is_manual_exposure: Optional[str] = None,
    ):
        if gate is not None:
            self.assertEqual(exposure.get('metadata', {}).get('gate'), gate)
        if config is not None:
            self.assertEqual(exposure.get('metadata', {}).get('config'), config)
        if is_manual_exposure is not None:
            self.assertEqual(exposure.get('metadata', {}).get(
                'isManualExposure'), is_manual_exposure)
