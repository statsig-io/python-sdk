import unittest
from typing import Callable, List
from unittest.mock import patch

from statsig import StatsigOptions, StatsigServer, StatsigUser, StatsigEvent
from network_stub import NetworkStub

_api_override = "http://evaluation-details-test"
_network_stub = NetworkStub(_api_override)


@patch('requests.post', side_effect=_network_stub.mock)
class TestBackgroundThreadSpawning(unittest.TestCase):
    _server: StatsigServer
    _user = StatsigUser(user_id="a-user")
    _event = StatsigEvent(_user, "an_event")
    _actions: List[Callable]

    @patch('requests.request', side_effect=_network_stub.mock)
    def setUp(self, mock_request) -> None:
        server = StatsigServer()
        options = StatsigOptions(
            api=_api_override,
            disable_diagnostics=True
        )

        _network_stub.reset()
        _network_stub.stub_request_with_value("log_event", 202, "")
        _network_stub.stub_request_with_value(
            "download_config_specs/.*", 500, "{}")

        server.initialize("secret-key", options)
        self._server = server

        self._actions = [
            lambda: self._server.check_gate(self._user, "a_gate"),
            lambda: self._server.get_config(self._user, "a_config"),
            lambda: self._server.get_experiment(self._user, "an_experiment"),
            lambda: self._server.get_layer(self._user, "an_experiment"),
            lambda: self._server.log_event(self._event)
        ]

    def test_logger_threads_restart(self, mock_request):
        self._logger_none_restart_test(self._actions)

    def test_logger_local_mode_threads_restart(self, mock_request):
        self._logger_local_mode_restart_test(self._actions)

    def test_logger_ead_threads_restart(self, mock_request):
        self._logger_dead_restart_test(self._actions)

    def test_spec_store_threads_restart(self, mock_request):
        self._spec_store_none_restart_test(self._actions)

    def test_spec_store_local_mode_threads_restart(self, mock_request):
        self._spec_store_local_mode_restart_test(self._actions)

    def test_spec_store_dead_threads_restart(self, mock_request):
        self._spec_store_dead_restart_test(self._actions)

    def _logger_none_restart_test(self, actions: List[Callable]):
        for action in actions:
            self._server._logger._background_flush = None
            self._server._logger._background_retry = None

            action()

            self.assertIsNotNone(self._server._logger._background_flush)
            self.assertIsNotNone(self._server._logger._background_retry)

    def _logger_local_mode_restart_test(self, actions: List[Callable]):
        for action in actions:
            self._server._logger._background_flush = None
            self._server._logger._background_retry = None
            self._server._logger._local_mode = True

            action()

            self.assertIsNone(self._server._logger._background_flush)
            self.assertIsNone(self._server._logger._background_retry)

    def _logger_dead_restart_test(self, actions: List[Callable]):
        def always_false():
            return False

        for action in actions:
            self._server._logger._background_flush.is_alive = always_false
            self._server._logger._background_retry.is_alive = always_false

            action()

            self.assertTrue(self._server._logger._background_flush.is_alive())
            self.assertTrue(self._server._logger._background_retry.is_alive())

    def _spec_store_none_restart_test(self, actions: List[Callable]):
        for action in actions:
            self._server._spec_store._background_download_configs = None
            self._server._spec_store._background_download_id_lists = None

            action()

            self.assertIsNotNone(
                self._server._spec_store.spec_updater._background_download_configs)
            self.assertIsNotNone(
                self._server._spec_store.spec_updater._background_download_id_lists)

    def _spec_store_local_mode_restart_test(self, actions: List[Callable]):
        for action in actions:
            self._server._spec_store._background_download_configs = None
            self._server._spec_store._background_download_id_lists = None
            self._server._options.local_mode = True

            action()

            self.assertIsNone(
                self._server._spec_store._background_download_configs)
            self.assertIsNone(
                self._server._spec_store._background_download_id_lists)

    def _spec_store_dead_restart_test(self, actions: List[Callable]):
        def always_false():
            return False

        for action in actions:
            self._server._spec_store.spec_updater._background_download_configs.is_alive = always_false
            self._server._spec_store.spec_updater._background_download_id_lists.is_alive = always_false

            action()

            self.assertTrue(
                self._server._spec_store.spec_updater._background_download_configs.is_alive())
            self.assertTrue(
                self._server._spec_store.spec_updater._background_download_id_lists.is_alive())


if __name__ == '__main__':
    unittest.main()
