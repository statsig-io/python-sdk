import unittest
from statsig.statsig_options import StatsigOptions
from statsig.statsig_server import StatsigServer
from statsig.statsig_user import StatsigUser


from tests.mockserver import MockServer


class LoggerTest(unittest.TestCase):
    _server: MockServer
    _requests: list

    @classmethod
    def setUpClass(cls):
        cls._server = MockServer(port=1236)
        cls._server.start()
        cls._events = 0

        def on_request():
            req = MockServer.get_request()
            
            if type(req.json) is dict:
                cls._events += len(req.json['events'])
            
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
        self.__class__._events = 0

    def test_log_size(self):
        self._instance.check_gate(self._user, "a_gate")
        self._instance.check_gate(self._user, "a_gate")
        
        self.assertEqual(self.__class__._events, 0)

        self._instance.check_gate(self._user, "a_gate")
        self.assertEqual(self.__class__._events, 3)

        self._instance.check_gate(self._user, "a_gate")
        self.assertEqual(self.__class__._events, 3)
        self._instance.check_gate(self._user, "a_gate")
        self._instance.check_gate(self._user, "a_gate")
        self.assertEqual(self.__class__._events, 6)


if __name__ == '__main__':
    unittest.main()
