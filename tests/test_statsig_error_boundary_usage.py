import unittest
from statsig.dynamic_config import DynamicConfig
from statsig.layer import Layer
from statsig.statsig_event import StatsigEvent

from statsig.statsig_options import StatsigOptions
from statsig.statsig_server import StatsigServer
from statsig.statsig_user import StatsigUser

from tests.mockserver import MockServer


class TestStatsigErrorBoundaryUsage(unittest.TestCase):
    _server: MockServer
    _requests: list
    _instance: StatsigServer
    _user: StatsigUser

    @classmethod
    def setUpClass(cls):
        cls._server = MockServer(port=1236)
        cls._server.start()
        cls._requests = []

        def on_request():
            req = MockServer.get_request()
            cls._requests.append({
                "path": req.path,
                "body": req.json,
                "headers": req.headers
            })
            return req.json

        cls._server.add_callback_response(
            "/v1/sdk_exception", on_request)

    @classmethod
    def tearDownClass(cls):
        cls._server.shutdown_server()

    def setUp(self):
        self._instance = StatsigServer()
        options = StatsigOptions(
            api=self._server.url,
        )
        self._instance.initialize("secret-key", options)
        self._user = StatsigUser("dloomb")

        self._instance._errorBoundary.endpoint = self._server.url + "/v1/sdk_exception"
        self._instance._evaluator = "_BAD_EVALUATOR_"
        self._instance._logger = "_BAD_LOGGER_"
        self.__class__._requests = []

    def test_errors_with_initialize(self):
        statsig = StatsigServer()
        statsig._errorBoundary.endpoint = self._server.url + "/v1/sdk_exception"
        statsig._download_config_specs = "_BAD_DOWNLOAD_"

        res = statsig.initialize("secret-key", StatsigOptions(
            api=self._server.url,
        ))

        trace = self._get_requests()[0]['body']['info']
        self.assertEqual(len(self._get_requests()), 1)
        self.assertIn('object is not callable', trace)
        self.assertFalse(res)
        self.assertTrue(statsig._initialized)

    def test_errors_with_check_gate(self):
        res = self._instance.check_gate(self._user, "a_gate")
        trace = self._get_requests()[0]['body']['info']

        self.assertEqual(len(self._get_requests()), 1)
        self.assertIn('object has no attribute \'check_gate\'\n', trace)
        self.assertFalse(res)

    def test_errors_with_get_config(self):
        res = self._instance.get_config(self._user, "a_config")
        trace = self._get_requests()[0]['body']['info']

        self.assertEqual(len(self._get_requests()), 1)
        self.assertIn('object has no attribute \'get_config\'\n', trace)
        self.assertIsInstance(res, DynamicConfig)
        self.assertEqual(res.value, {})
        self.assertEqual(res.name, "a_config")

    def test_errors_with_get_experiment(self):
        res = self._instance.get_experiment(self._user, "an_experiment")
        trace = self._get_requests()[0]['body']['info']

        self.assertEqual(len(self._get_requests()), 1)
        self.assertIn('object has no attribute \'get_config\'\n', trace)
        self.assertIsInstance(res, DynamicConfig)
        self.assertEqual(res.value, {})
        self.assertEqual(res.name, "an_experiment")

    def test_errors_with_get_layer(self):
        res = self._instance.get_layer(self._user, "a_layer")
        trace = self._get_requests()[0]['body']['info']

        self.assertEqual(len(self._get_requests()), 1)
        self.assertIn('object has no attribute \'get_layer\'\n', trace)
        self.assertIsInstance(res, Layer)
        self.assertEqual(res.name, "a_layer")

    def test_errors_with_log_event(self):
        res = self._instance.log_event(StatsigEvent(self._user, "an_event"))
        trace = self._get_requests()[0]['body']['info']

        self.assertEqual(len(self._get_requests()), 1)
        self.assertIn('object has no attribute \'log\'\n', trace)
        self.assertIsNone(res)

    def test_errors_with_shutdown(self):
        res = self._instance.shutdown()
        trace = self._get_requests()[0]['body']['info']

        self.assertEqual(len(self._get_requests()), 1)
        self.assertIn('object has no attribute \'shutdown\'\n', trace)
        self.assertIsNone(res)

    def test_errors_with_override_gate(self):
        res = self._instance.override_gate("a_gate", False)
        trace = self._get_requests()[0]['body']['info']

        self.assertEqual(len(self._get_requests()), 1)
        self.assertIn('object has no attribute \'override_gate\'\n', trace)
        self.assertIsNone(res)

    def test_errors_with_override_config(self):
        res = self._instance.override_config("a_config", {})
        trace = self._get_requests()[0]['body']['info']

        self.assertEqual(len(self._get_requests()), 1)
        self.assertIn('object has no attribute \'override_config\'\n', trace)
        self.assertIsNone(res)

    def test_errors_with_override_experiment(self):
        res = self._instance.override_experiment("an_experiment", {})
        trace = self._get_requests()[0]['body']['info']

        self.assertEqual(len(self._get_requests()), 1)
        self.assertIn('object has no attribute \'override_config\'\n', trace)
        self.assertIsNone(res)

    def test_errors_with_evaluate_all(self):
        res = self._instance.evaluate_all(self._user)
        trace = self._get_requests()[0]['body']['info']

        self.assertEqual(len(self._get_requests()), 1)
        self.assertIn('object has no attribute \'get_all_gates\'\n', trace)
        self.assertEqual(res, {
            "feature_gates": {}, "dynamic_configs": {}
        })

    def _get_requests(self):
        return self.__class__._requests


if __name__ == '__main__':
    unittest.main()
