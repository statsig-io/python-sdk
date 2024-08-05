import random
import unittest
from unittest.mock import patch

from gzip_helpers import GzipHelpers
from statsig import globals
from statsig.statsig_event import StatsigEvent
from statsig.statsig_options import StatsigOptions
from statsig.statsig_server import StatsigServer
from statsig.statsig_user import StatsigUser
import threading

from time import sleep

from network_stub import NetworkStub


class LoggerTest(unittest.TestCase):
    _network_stub = NetworkStub("http://logger-test")
    _events: list
    _didLog = threading.Event()

    def setUp(self):
        self._instance = StatsigServer()
        options = StatsigOptions(
            api="http://logger-test",
            event_queue_size=3,
            disable_diagnostics=True,
            rulesets_sync_interval=100000, #Skip config sync and avoid diagnostics event
            idlists_sync_interval=100000 #Skip config sync and avoid diagnostics event
        )

        self._network_stub.reset()
        self._events = []

        def on_log(url: str, **kwargs):
            new_events = GzipHelpers.decode_body(kwargs)["events"]
            if(len(new_events) > 0):
                self._events += new_events
                self._didLog.set()

        self._network_stub.stub_request_with_function("log_event", 202, on_log)

        globals.STATSIG_LOGGING_INTERVAL_SECONDS = 1
        self._instance.initialize("secret-key", options)
        self._user = StatsigUser("dloomb")
        
        ## clear diagnostics initialize log
        self.flush()

    def tearDown(self):
        globals.STATSIG_LOGGING_INTERVAL_SECONDS = 5.0
        self._instance.shutdown()

    @patch('requests.request', side_effect=_network_stub.mock)
    def flush(self, mock_request):
        self._instance.flush()

    @patch('requests.request', side_effect=_network_stub.mock)
    def test_log_size(self, mock_request):
        self._instance.check_gate(self._user, "a_gate")
        self._instance.check_gate(self._user, "b_gate")

        self.assertEqual(len(self._events), 0)

        self._run_and_wait_for_logs(lambda: self._instance.check_gate(self._user, "c_gate"))
        self.assertEqual(len(self._events), 3)

        self._instance.check_gate(self._user, "d_gate")
        self.assertEqual(len(self._events), 3)

        self._instance.check_gate(self._user, "e_gate")

        self._run_and_wait_for_logs(lambda: self._instance.check_gate(self._user, "f_gate"))
        self.assertEqual(len(self._events), 6)

    @patch('requests.request', side_effect=_network_stub.mock)
    def test_exposure_dedupe(self, mock_request):
        self._instance.check_gate(self._user, "a_gate")
        self._instance.check_gate(self._user, "a_gate")

        self.assertEqual(len(self._events), 0)

        self._instance.check_gate(self._user, "a_gate")
        # does not flush yet, because they are deduped
        self.assertEqual(len(self._events), 0)

        self._instance.check_gate(self._user, "b_gate")
        self.assertEqual(len(self._events), 0)

        self._run_and_wait_for_logs(lambda: self._instance.check_gate(self._user, "c_gate"))
        self.assertEqual(len(self._events), 3)

        self._instance.check_gate(self._user, "a_gate")
        self._instance.check_gate(self._user, "b_gate")
        self._instance.check_gate(self._user, "c_gate")
        self.assertEqual(len(self._events), 3)

        def __log_gates():
            self._instance.get_config(self._user, "a_gate")
            self._instance.get_config(self._user, "b_gate")
            self._instance.get_config(self._user, "b_gate")
            self._instance.get_config(self._user, "b_gate")
            self._instance.get_config(self._user, "a_gate")
            self._instance.get_config(self._user, "c_gate")

        self._run_and_wait_for_logs(__log_gates)
        self.assertEqual(len(self._events), 6)

        self._instance.check_gate(self._user, "d_gate")
        self._run_and_wait_for_logs(lambda: self._instance.flush())
        self.assertEqual(len(self._events), 7)

        # get layer does not expose
        self._instance.get_layer(self._user, "a_gate")
        self._instance.get_layer(self._user, "b_gate")
        self._instance.get_layer(self._user, "c_gate")
        self.assertEqual(len(self._events), 7)

        def __get_experiments():
            self._instance.get_experiment(StatsigUser(str(random.randint(1, 10000000000))), "a_gate")
            self._instance.get_experiment(StatsigUser(str(random.randint(1, 10000000000))), "a_gate")
            self._instance.get_experiment(StatsigUser(str(random.randint(1, 10000000000))), "a_gate")

        self._run_and_wait_for_logs(__get_experiments)
        self.assertEqual(len(self._events), 10)

    @patch('requests.request', side_effect=_network_stub.mock)
    def test_log_content(self, mock_request):
        self._instance.check_gate(self._user, "a_gate")
        sleep(0.1)
        self._instance.get_config(self._user, "a_config")
        sleep(0.1)

        evt = StatsigEvent(self._user, "my_event", 10)
        self._run_and_wait_for_logs(lambda: self._instance.log_event(evt))        

        self.assertEqual(len(self._events), 3)
        gate_exposure = self._events[0]
        config_exposure = self._events[1]
        log_event = self._events[2]

        self.assertNotEqual(gate_exposure["time"], config_exposure["time"])
        self.assertEqual("a_gate", gate_exposure["metadata"]["gate"])
        self.assertEqual("false", gate_exposure["metadata"]["gateValue"])
        self.assertEqual("", gate_exposure["metadata"]["ruleID"])

        self.assertNotEqual(config_exposure["time"], log_event["time"])
        self.assertEqual("a_config", config_exposure["metadata"]["config"])
        self.assertEqual("", config_exposure["metadata"]["ruleID"])

        self.assertFalse("metadata" in log_event)
        self.assertEqual(10, log_event["value"])

    def _run_and_wait_for_logs(self, task):
        self._didLog = threading.Event()
        task()
        self._didLog.wait(2)


if __name__ == '__main__':
    unittest.main()
