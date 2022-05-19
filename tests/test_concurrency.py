import threading
import time
import os
import unittest
import json
from .mockserver import MockServer

from statsig import statsig, StatsigUser, StatsigOptions, StatsigEvent, StatsigEnvironmentTier

with open(os.path.join(os.path.abspath(os.path.dirname(__file__)), '../testdata/download_config_specs.json')) as r:
    CONFIG_SPECS_RESPONSE = r.read()


class TestStatsigConcurrency(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.server = MockServer(port=1234)
        cls.server.start()
        cls.server.add_json_response(
            "/download_config_specs", json.loads(CONFIG_SPECS_RESPONSE))
        cls.server.add_json_response(
            "/get_id_lists", json.loads("{}"))
        cls.server.add_log_event_response(
            cls._count_logs.__get__(cls, cls.__class__))
        cls.event_count = 0
        cls.statsig_user = StatsigUser(
            "123", email="testuser@statsig.com", private_attributes={"test": 123})
        cls.random_user = StatsigUser("random")
        cls.logs = {}
        options = StatsigOptions(
            api=cls.server.url, tier=StatsigEnvironmentTier.development)

        statsig.initialize("secret-key", options)
        cls.initTime = round(time.time() * 1000)

    def test_checking_concurrently(self):
        self.threads = []
        for x in range(10):
            thread = threading.Thread(
                target=self.run_checks, args=(0.01, 20))
            thread.start()
            self.threads.append(thread)

        for t in self.threads:
            t.join()

        self.assertEqual(600, len(statsig.get_instance()._logger._events))
        self.assertEqual(1000, self.event_count)
        statsig.shutdown()

        self.assertEqual(0, len(statsig.get_instance()._logger._events))
        self.assertEqual(1600, self.event_count)

    def run_checks(self, interval, times):
        for x in range(times):
            user = StatsigUser(
                f'user_id_{x}', email="testuser@statsig.com", private_attributes={"test": 123})
            statsig.log_event(StatsigEvent(
                user, "test_event", 1, {"key": "value"}))
            self.assertEqual(True, statsig.check_gate(
                user, "on_for_statsig_email"))
            self.assertEqual(True, statsig.check_gate(user, "always_on_gate"))

            statsig.log_event(StatsigEvent(
                user, "test_event_2", 1, {"key": "value"}))
            exp_param = statsig.get_experiment(
                user, "sample_experiment").get("experiment_param", "default")
            self.assertTrue(exp_param == "test" or exp_param == "control")

            statsig.log_event(StatsigEvent(
                user, "test_event_3", 1, {"key": "value"}))
            self.assertEqual(7, statsig.get_config(
                user, "test_config").get("number", 0))
            self.assertTrue(statsig.get_layer(
                user, "a_layer").get("layer_param", False))

            time.sleep(interval)

    def _count_logs(self, json):
        self.event_count += len(json["events"])

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown_server()


if __name__ == '__main__':
    unittest.main()
