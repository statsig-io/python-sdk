import unittest
from unittest.mock import patch

from statsig import StatsigOptions, StatsigServer, StatsigUser
from network_stub import NetworkStub

_api_override = "http://concurrency-on-init-test"
_network_stub = NetworkStub(_api_override)


def _mock_thread_start(**kwargs):
    raise RuntimeError("Failed to start thread")


@patch('requests.request', side_effect=_network_stub.mock)
class TestConcurrencyOnInit(unittest.TestCase):
    _server: StatsigServer
    _user = StatsigUser(user_id="a-user")

    @patch('requests.request', side_effect=_network_stub.mock)
    def setUp(self, mock_request) -> None:
        self._server = StatsigServer()

    @patch('threading.Thread.start', side_effect=_mock_thread_start)
    def test_initialize_works_when_threads_throw(
            self, _mock_request, _mock_start):
        self._server.initialize("secret-key", StatsigOptions(
            api=_api_override,
            disable_diagnostics=True
        ))

        self.assertTrue(self._server._initialized)
        self.assertIsNotNone(self._server._logger)
        self.assertIsNotNone(self._server._spec_store)
        self.assertIsNotNone(self._server._evaluator)


if __name__ == '__main__':
    unittest.main()
