import unittest
from unittest.mock import patch

from statsig.statsig_event import StatsigEvent
from statsig.statsig_options import StatsigOptions
from statsig.statsig_server import StatsigServer
from statsig.statsig_user import StatsigUser

from time import sleep

from tests.network_stub import NetworkStub


class LoggerTest(unittest.TestCase):
    _network_stub = NetworkStub("http://logger-test")
    _events: list

    def setUp(self):
        self._instance = StatsigServer()
        options = StatsigOptions(
            api="http://logger-test",
            event_queue_size=3,
        )

        self._network_stub.reset()
        self._events = []

        def on_log(url: str, data: dict):
            self._events += data["json"]["events"]

        self._network_stub.stub_request_with_function("log_event", 202, on_log)

        self._instance.initialize("secret-key", options)
        self._user = StatsigUser("dloomb")

    @patch('requests.post', side_effect=_network_stub.mock)
    def test_log_size(self, mock_post):
        self._instance.check_gate(self._user, "a_gate")
        self._instance.check_gate(self._user, "a_gate")

        self.assertEqual(len(self._events), 0)

        self._instance.check_gate(self._user, "a_gate")
        self.assertEqual(len(self._events), 3)

        self._instance.check_gate(self._user, "a_gate")
        self.assertEqual(len(self._events), 3)
        self._instance.check_gate(self._user, "a_gate")
        self._instance.check_gate(self._user, "a_gate")
        self.assertEqual(len(self._events), 6)

        self._instance.check_gate(self._user, "a_gate")
        self._instance.flush()
        self.assertEqual(len(self._events), 7)

    @patch('requests.post', side_effect=_network_stub.mock)
    def test_log_content(self, mock_post):
        self._instance.check_gate(self._user, "a_gate")
        sleep(1)
        self._instance.get_config(self._user, "a_config")
        sleep(1)

        evt = StatsigEvent(self._user, "my_event", 10)
        self._instance.log_event(evt)

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


if __name__ == '__main__':
    unittest.main()
