import unittest
from unittest.mock import patch

import statsig.statsig
import random

from statsig import globals, StatsigServer, StatsigOptions, StatsigUser
from tests.network_stub import NetworkStub


class LoggerTest(unittest.TestCase):
    _network_stub = NetworkStub("http://logger-worker-test")

    def setUp(self):
        self._instance = StatsigServer()
        options = StatsigOptions(
            api="http://logger-worker-test",
            disable_diagnostics=True,
            rulesets_sync_interval=100000,  # Skip config sync and avoid diagnostics event
            idlists_sync_interval=100000  # Skip config sync and avoid diagnostics event
        )

        self._network_stub.reset()

        self._network_stub.stub_request_with_value("log_event", 202, {})
        self._instance.initialize("secret-key", options)
        self._user = StatsigUser("dloomb")

        ## clear diagnostics initialize log
        self.flush()


    @patch('requests.request', side_effect=_network_stub.mock)
    def flush(self, mock_request):
        self._instance.flush()

    def test_backoff_intervals(self):
        ease_out_backoff_intervals = [5, 10, 20, 40, 80, 120, 120, 120, 120, 120]
        ease_in_backoff_intervals = [120, 60, 30, 15, 7.5, 5, 5, 5, 5, 5]

        actual_out_intervals = []
        actual_in_intervals = []

        for i in range(10):
            curr_interval = self._instance._logger._logger_worker._log_interval
            actual_out_intervals.append(curr_interval)
            self._instance._logger._logger_worker._failure_backoff()

        are_equal = all(float(a) == float(b) for a, b in zip(ease_out_backoff_intervals, actual_out_intervals))
        self.assertTrue(are_equal)

        for i in range(10):
            curr_interval = self._instance._logger._logger_worker._log_interval
            actual_in_intervals.append(curr_interval)
            self._instance._logger._logger_worker._success_backoff()

        are_equal = all(float(a) == float(b) for a, b in zip(ease_in_backoff_intervals, actual_in_intervals))
        self.assertTrue(are_equal)


    def test_variable_backoff_intervals(self):
        out_of_range = False

        def randomly_backoff():
            which_backoff = random.choice([True, False])
            if which_backoff:
                self._instance._logger._logger_worker._failure_backoff()
            else:
                self._instance._logger._logger_worker._success_backoff()

        for i in range(50):
            curr_interval = self._instance._logger._logger_worker._log_interval
            if curr_interval < 5 or curr_interval > 120:
                out_of_range = True
                break
            randomly_backoff()

        self.assertFalse(out_of_range)
