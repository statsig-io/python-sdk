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


@patch('requests.post', side_effect=mocked_post)
class TestStatsigErrorBoundaryUsage(unittest.TestCase):
    _instance: StatsigServer
    _user: StatsigUser
    requests = []

    def setUp(self):
        self._instance = StatsigServer()
        self._instance.initialize("secret-key")
        self._user = StatsigUser("dloomb")

        self._instance._evaluator = "_BAD_EVALUATOR_"  # type: ignore - intentional
        self._instance._logger = "_BAD_LOGGER_"  # type: ignore - intentional
        TestStatsigErrorBoundaryUsage.requests = []

    def test_errors_with_initialize(self, mock_post):
        statsig = StatsigServer()
        statsig._download_config_specs = "_BAD_DOWNLOAD_"  # type: ignore - intentional

        res = statsig.initialize("secret-key")

        self.assertEqual(len(self._get_requests()), 1)
        trace = self._get_requests()[0]['body']['info']
        self.assertIn('object is not callable', trace)
        self.assertFalse(res)
        self.assertTrue(statsig._initialized)

    def test_errors_with_check_gate(self, mock_post):
        res = self._instance.check_gate(self._user, "a_gate")

        self.assertEqual(len(self._get_requests()), 1)
        trace = self._get_requests()[0]['body']['info']
        self.assertIn('object has no attribute \'check_gate\'\n', trace)
        self.assertFalse(res)

    def test_errors_with_get_config(self, mock_post):
        res = self._instance.get_config(self._user, "a_config")

        self.assertEqual(len(self._get_requests()), 1)
        trace = self._get_requests()[0]['body']['info']
        self.assertIn('object has no attribute \'get_config\'\n', trace)
        self.assertIsInstance(res, DynamicConfig)
        self.assertEqual(res.value, {})
        self.assertEqual(res.name, "a_config")

    def test_errors_with_get_experiment(self, mock_post):
        res = self._instance.get_experiment(self._user, "an_experiment")

        self.assertEqual(len(self._get_requests()), 1)
        trace = self._get_requests()[0]['body']['info']
        self.assertIn('object has no attribute \'get_config\'\n', trace)
        self.assertIsInstance(res, DynamicConfig)
        self.assertEqual(res.value, {})
        self.assertEqual(res.name, "an_experiment")

    def test_errors_with_get_layer(self, mock_post):
        res = self._instance.get_layer(self._user, "a_layer")

        self.assertEqual(len(self._get_requests()), 1)
        trace = self._get_requests()[0]['body']['info']
        self.assertIn('object has no attribute \'get_layer\'\n', trace)
        self.assertIsInstance(res, Layer)
        self.assertEqual(res.name, "a_layer")

    def test_errors_with_log_event(self, mock_post):
        res = self._instance.log_event(StatsigEvent(self._user, "an_event"))

        self.assertEqual(len(self._get_requests()), 1)
        trace = self._get_requests()[0]['body']['info']
        self.assertIn('object has no attribute \'log\'\n', trace)
        self.assertIsNone(res)

    def test_errors_with_shutdown(self, mock_post):
        res = self._instance.shutdown()

        self.assertEqual(len(self._get_requests()), 1)
        trace = self._get_requests()[0]['body']['info']
        self.assertIn('object has no attribute \'shutdown\'\n', trace)
        self.assertIsNone(res)

    def test_errors_with_override_gate(self, mock_post):
        res = self._instance.override_gate("a_gate", False)

        self.assertEqual(len(self._get_requests()), 1)
        trace = self._get_requests()[0]['body']['info']
        self.assertIn('object has no attribute \'override_gate\'\n', trace)
        self.assertIsNone(res)

    def test_errors_with_override_config(self, mock_post):
        res = self._instance.override_config("a_config", {})

        self.assertEqual(len(self._get_requests()), 1)
        trace = self._get_requests()[0]['body']['info']
        self.assertIn('object has no attribute \'override_config\'\n', trace)
        self.assertIsNone(res)

    def test_errors_with_override_experiment(self, mock_post):
        res = self._instance.override_experiment("an_experiment", {})

        self.assertEqual(len(self._get_requests()), 1)
        trace = self._get_requests()[0]['body']['info']
        self.assertIn('object has no attribute \'override_config\'\n', trace)
        self.assertIsNone(res)

    def test_errors_with_evaluate_all(self, mock_post):
        res = self._instance.evaluate_all(self._user)

        self.assertEqual(len(self._get_requests()), 1)
        trace = self._get_requests()[0]['body']['info']
        self.assertIn('object has no attribute \'get_all_gates\'\n', trace)
        self.assertEqual(res, {
            "feature_gates": {}, "dynamic_configs": {}
        })

    def _get_requests(self):
        return TestStatsigErrorBoundaryUsage.requests


if __name__ == '__main__':
    unittest.main()
