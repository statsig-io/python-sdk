import unittest

from statsig.dynamic_config import DynamicConfig
from statsig.layer import Layer
from statsig.statsig_event import StatsigEvent
from statsig.statsig_server import StatsigServer
from statsig.statsig_user import StatsigUser
from unittest.mock import patch


def mocked_post(*args, **kwargs):
    TestStatsigErrorBoundaryUsage.requests.append({
        "url": args[0],
        "body": kwargs['json'],
        "headers": kwargs['headers']
    })


def _get_requests(statsig):
    statsig._errorBoundary.shutdown(True)
    return TestStatsigErrorBoundaryUsage.requests


@patch('requests.post', side_effect=mocked_post)
class TestStatsigErrorBoundaryUsage(unittest.TestCase):
    _instance: StatsigServer
    _user: StatsigUser
    requests = []

    def setUp(self):
        self._instance = StatsigServer()
        self._instance._errorBoundary._is_silent = True
        self._instance.initialize("secret-key")
        self._user = StatsigUser("dloomb")

        class FakeWithSpawnMethod:
            def spawn_bg_threads_if_needed(self):
                pass

        # Setup to cause crashes
        self._instance._spec_store = FakeWithSpawnMethod()
        self._instance._logger = FakeWithSpawnMethod()
        self._instance._evaluator = "_BAD_EVALUATOR_"

        TestStatsigErrorBoundaryUsage.requests = []

    def tearDown(self) -> None:
        self._instance.shutdown()

    def test_errors_with_initialize(self, mock_post):
        statsig = StatsigServer()
        TestStatsigErrorBoundaryUsage.requests = []
        statsig.initialize("secret-key", "_BAD_OPTIONS_")
        

        self.assertEqual(len(_get_requests(statsig)), 1)
        trace = _get_requests(self._instance)[0]['body']['info']
        self.assertIn(
            "AttributeError: 'str' object has no attribute 'api_for_download_config_specs'", trace)
        self.assertTrue(statsig._initialized)

    def test_errors_with_check_gate(self, mock_post):
        res = self._instance.check_gate(self._user, "a_gate")

        self.assertEqual(len(_get_requests(self._instance)), 1)
        trace = _get_requests(self._instance)[0]['body']['info']
        self.assertIn('object has no attribute \'check_gate\'\n', trace)
        self.assertFalse(res)

    def test_errors_with_get_config(self, mock_post):
        res = self._instance.get_config(self._user, "a_config")

        self.assertEqual(len(_get_requests(self._instance)), 1)
        trace = _get_requests(self._instance)[0]['body']['info']
        self.assertIn('object has no attribute \'get_config\'\n', trace)
        self.assertIsInstance(res, DynamicConfig)
        self.assertEqual(res.value, {})
        self.assertEqual(res.name, "a_config")

    def test_errors_with_get_experiment(self, mock_post):
        res = self._instance.get_experiment(self._user, "an_experiment")

        self.assertEqual(len(_get_requests(self._instance)), 1)
        trace = _get_requests(self._instance)[0]['body']['info']
        self.assertIn('object has no attribute \'get_config\'\n', trace)
        self.assertIsInstance(res, DynamicConfig)
        self.assertEqual(res.value, {})
        self.assertEqual(res.name, "an_experiment")

    def test_errors_with_get_layer(self, mock_post):
        res = self._instance.get_layer(self._user, "a_layer")

        self.assertEqual(len(_get_requests(self._instance)), 1)
        trace = _get_requests(self._instance)[0]['body']['info']
        self.assertIn('object has no attribute \'get_layer\'\n', trace)
        self.assertIsInstance(res, Layer)
        self.assertEqual(res.name, "a_layer")

    def test_errors_with_log_event(self, mock_post):
        self._instance.log_event(StatsigEvent(self._user, "an_event"))

        self.assertEqual(len(_get_requests(self._instance)), 1)
        trace = _get_requests(self._instance)[0]['body']['info']
        self.assertIn('object has no attribute \'log\'\n', trace)

    def test_errors_with_shutdown(self, mock_post):
        self._instance.shutdown()

        self.assertEqual(len(_get_requests(self._instance)), 1)
        trace = _get_requests(self._instance)[0]['body']['info']
        self.assertIn('object has no attribute \'shutdown\'\n', trace)

    def test_errors_with_override_gate(self, mock_post):
        self._instance.override_gate("a_gate", False)

        self.assertEqual(len(_get_requests(self._instance)), 1)
        trace = _get_requests(self._instance)[0]['body']['info']
        self.assertIn('object has no attribute \'override_gate\'\n', trace)

    def test_errors_with_override_config(self, mock_post):
        self._instance.override_config("a_config", {})

        self.assertEqual(len(_get_requests(self._instance)), 1)
        trace = _get_requests(self._instance)[0]['body']['info']
        self.assertIn('object has no attribute \'override_config\'\n', trace)

    def test_errors_with_override_experiment(self, mock_post):
        self._instance.override_experiment("an_experiment", {})

        self.assertEqual(len(_get_requests(self._instance)), 1)
        trace = _get_requests(self._instance)[0]['body']['info']
        self.assertIn('object has no attribute \'override_config\'\n', trace)

    def test_errors_with_evaluate_all(self, mock_post):
        res = self._instance.evaluate_all(self._user)

        self.assertEqual(len(_get_requests(self._instance)), 1)
        trace = _get_requests(self._instance)[0]['body']['info']
        self.assertIn('object has no attribute \'get_all_gates\'\n', trace)
        self.assertEqual(res, {
            "feature_gates": {}, "dynamic_configs": {}
        })


if __name__ == '__main__':
    unittest.main()
