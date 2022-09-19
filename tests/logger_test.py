import unittest
from statsig.statsig_event import StatsigEvent
from statsig.statsig_options import StatsigOptions
from statsig.statsig_server import StatsigServer
from statsig.statsig_user import StatsigUser

from time import sleep
from tests.mockserver import MockServer


class LoggerTest(unittest.TestCase):
    _server: MockServer
    _requests: list

    @classmethod
    def setUpClass(cls):
        cls._server = MockServer(port=1236)
        cls._server.start()
        cls._events = []

        def on_request():
            req = MockServer.get_request()
            
            if type(req.json) is dict:
                cls._events += req.json['events']
            return req.json

        cls._server.add_callback_response(
            "/log_event", on_request)

    @classmethod
    def tearDownClass(cls):
        cls._server.shutdown_server()

    def setUp(self):
        self._instance = StatsigServer()
        options = StatsigOptions(
            api=self._server.url,
            event_queue_size=3,
        )
        self._instance.initialize("secret-key", options)
        self._user = StatsigUser("dloomb")
        self.__class__._events = []

    def test_log_size(self):
        self._instance.check_gate(self._user, "a_gate")
        self._instance.check_gate(self._user, "a_gate")
        
        self.assertEqual(len(self.__class__._events), 0)

        self._instance.check_gate(self._user, "a_gate")
        self.assertEqual(len(self.__class__._events), 3)

        self._instance.check_gate(self._user, "a_gate")
        self.assertEqual(len(self.__class__._events), 3)
        self._instance.check_gate(self._user, "a_gate")
        self._instance.check_gate(self._user, "a_gate")
        self.assertEqual(len(self.__class__._events), 6)
    
    def test_log_content(self):
        self._instance.check_gate(self._user, "a_gate")
        sleep(1)
        self._instance.get_config(self._user, "a_config")
        sleep(1)
        
        evt = StatsigEvent(self._user, "my_event", 10)
        self._instance.log_event(evt)

        self.assertEqual(len(self.__class__._events), 3)
        gate_exposure = self.__class__._events[0]
        config_exposure = self.__class__._events[1]
        log_event = self.__class__._events[2]

        self.assertNotEqual(gate_exposure["time"], config_exposure["time"])
        self.assertDictEqual(gate_exposure["metadata"], {
                "gate": "a_gate",
                "gateValue": "false",
                "ruleID": ""
        })
        self.assertNotEqual(config_exposure["time"], log_event["time"])
        
        self.assertDictEqual(config_exposure["metadata"], {
                "config": "a_config",
                "ruleID": ""
        })

        self.assertFalse("metadata" in log_event)
        self.assertEqual(10, log_event["value"])




if __name__ == '__main__':
    unittest.main()
