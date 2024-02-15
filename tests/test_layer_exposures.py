import unittest
import os
import json
from unittest.mock import patch

from network_stub import NetworkStub
from statsig import statsig, StatsigUser, StatsigOptions, StatsigEnvironmentTier, Layer
from gzip_helpers import GzipHelpers
from test_case_with_extras import TestCaseWithExtras

with open(os.path.join(os.path.abspath(os.path.dirname(__file__)),
                       '../testdata/layer_exposures_download_config_specs.json')) as r:
    CONFIG_SPECS_RESPONSE = r.read()

methods = ['get', 'get_typed']

_network_stub = NetworkStub("http://test-layer-exposure")


@patch('requests.request', side_effect=_network_stub.mock)
class TestLayerExposures(TestCaseWithExtras):
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
            disable_diagnostics=True)

    def tearDown(self) -> None:
        statsig.shutdown()

    def test_does_not_log_on_get_layer(self, mock_request):
        self._start()
        statsig.get_layer(self._user, 'unallocated_layer')
        statsig.shutdown()

        events = TestLayerExposures._logs["events"]
        self.assertEqual(len(events), 0)

    def test_does_not_log_on_invalid_type(self, mock_request):
        self._start()
        layer = statsig.get_layer(self._user, 'unallocated_layer')
        layer.get_typed('an_int', 'err')
        statsig.shutdown()

        events = TestLayerExposures._logs["events"]
        self.assertEqual(len(events), 0)

    def test_does_not_log_non_existent_keys(self, mock_request):
        for method in methods:
            with self.subTest('with method ' + method, method=method):
                self._start()
                layer = statsig.get_layer(self._user, 'unallocated_layer')
                getattr(Layer, method)(layer, 'a_string', 'err')
                statsig.shutdown()

                events = TestLayerExposures._logs["events"]
                self.assertEqual(len(events), 0)

    def test_unallocated_layer_logging(self, mock_request):
        for method in methods:
            with self.subTest('with method ' + method, method=method):
                self._start()
                layer = statsig.get_layer(self._user, 'unallocated_layer')
                getattr(Layer, method)(layer, 'an_int', 0)
                statsig.shutdown()

                events = TestLayerExposures._logs["events"]
                self.assertEqual(len(events), 1)

                self.assertSubsetOf({
                    'config': 'unallocated_layer',
                    'ruleID': 'default',
                    'allocatedExperiment': '',
                    'parameterName': 'an_int',
                    'isExplicitParameter': 'false'
                }, events[0].get('metadata', {}))

    def test_explicit_vs_implicit_parameter_logging(self, mock_request):
        for method in methods:
            with self.subTest('with method ' + method, method=method):
                self._start()
                layer = statsig.get_layer(
                    self._user, 'explicit_vs_implicit_parameter_layer')
                getattr(Layer, method)(layer, 'an_int', 0)
                getattr(Layer, method)(layer, 'a_string', 'err')
                statsig.shutdown()

                events = TestLayerExposures._logs["events"]
                self.assertEqual(len(events), 2)

                self.assertSubsetOf({
                    'config': 'explicit_vs_implicit_parameter_layer',
                    'ruleID': 'alwaysPass',
                    'allocatedExperiment': 'experiment',
                    'parameterName': 'an_int',
                    'isExplicitParameter': 'true'
                }, events[0].get('metadata', {}))

                self.assertSubsetOf({
                    'config': 'explicit_vs_implicit_parameter_layer',
                    'ruleID': 'alwaysPass',
                    'allocatedExperiment': '',
                    'parameterName': 'a_string',
                    'isExplicitParameter': 'false'
                }, events[1].get('metadata', {}))

    def test_different_object_type_logging(self, mock_request):
        for method in methods:
            with self.subTest('with method ' + method, method=method):
                self._start()
                layer = statsig.get_layer(
                    self._user, 'different_object_type_logging_layer')
                getattr(Layer, method)(layer, 'a_bool', False)
                getattr(Layer, method)(layer, 'an_int', 0)
                getattr(Layer, method)(layer, 'a_double', 0.0)
                getattr(Layer, method)(layer, 'a_long', 0)
                getattr(Layer, method)(layer, 'a_string', 'err')
                getattr(Layer, method)(layer, 'an_array', [])
                getattr(Layer, method)(layer, 'an_object', {})
                statsig.shutdown()

                events = TestLayerExposures._logs["events"]
                self.assertEqual(len(events), 7)

                self.assertEqual("a_bool", events[0].get(
                    'metadata', {}).get('parameterName', ''))
                self.assertEqual("an_int", events[1].get(
                    'metadata', {}).get('parameterName', ''))
                self.assertEqual("a_double", events[2].get(
                    'metadata', {}).get('parameterName', ''))
                self.assertEqual("a_long", events[3].get(
                    'metadata', {}).get('parameterName', ''))
                self.assertEqual("a_string", events[4].get(
                    'metadata', {}).get('parameterName', ''))
                self.assertEqual("an_array", events[5].get(
                    'metadata', {}).get('parameterName', ''))
                self.assertEqual("an_object", events[6].get(
                    'metadata', {}).get('parameterName', ''))

    def test_logs_user_and_event_name(self, mock_request):
        for method in methods:
            with self.subTest('with method ' + method, method=method):
                self._start()
                layer = statsig.get_layer(StatsigUser("dloomb", "d@loomb.com"),
                                          'unallocated_layer')
                getattr(Layer, method)(layer, 'an_int', 0)
                statsig.shutdown()

                events = TestLayerExposures._logs["events"]
                self.assertEqual(len(events), 1)

                self.assertEqual('statsig::layer_exposure',
                                 events[0].get('eventName', ''))
                self.assertEqual({
                    'userID': 'dloomb',
                    'email': 'd@loomb.com',
                    'statsigEnvironment': {'tier': 'development'},
                },
                    events[0].get('user', {}))

    def _check_logs(self, json):
        TestLayerExposures._logs = json

    def _start(self):
        TestLayerExposures._logs = {'events': []}
        statsig.initialize("secret-key", self.options)


if __name__ == '__main__':
    unittest.main()
