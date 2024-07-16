import unittest
from unittest.mock import patch
from urllib.parse import urlparse

from statsig import statsig, StatsigOptions, StatsigUser
from network_stub import NetworkStub

_api_stubs = {
    "download_config_specs": NetworkStub("http://test-dcs"),
    "get_id_lists": NetworkStub("http://test-get-id-lists"),
    "log_event": NetworkStub("http://test-log-event"),
    "api": NetworkStub("http://test-api")
}

def mock_apis(*args, **kwargs):
    url = urlparse(args[1])
    for stub in _api_stubs.values():
        if stub.host in url.scheme + "://" + url.hostname:
            return stub.mock(*args, **kwargs)


@patch('requests.request', side_effect=mock_apis)
class TestApiOverrides(unittest.TestCase):
    @classmethod
    @patch('requests.request', side_effect=mock_apis)
    def setUpClass(cls, mock_request):
        cls.api_override = False
        cls.log_event_override = False
        cls.dcs_override = False
        cls.get_id_lists_override = False

        def on_log(url, **kwargs):
            if url.hostname == "test-api":
                cls.api_override = True
            if url.hostname == "test-log-event":
                cls.log_event_override = True
            if url.hostname == "test-dcs":
                cls.dcs_override = True
            if url.hostname == "test-get-id-lists":
                cls.get_id_lists_override = True

        _api_stubs["api"].stub_request_with_function(".*", 202, on_log)
        _api_stubs["download_config_specs"].stub_request_with_function(".*", 202, on_log)
        _api_stubs["get_id_lists"].stub_request_with_function(".*", 200, on_log)
        _api_stubs["log_event"].stub_request_with_function(".*", 202, on_log)

    @classmethod
    def tearDownClass(cls):
        cls.api_override = False
        cls.log_event_override = False
        cls.dcs_override = False
        cls.get_id_lists_override = False
        statsig.shutdown()

    def setUp(self):
        # Reset class variables before each test
        self.__class__.api_override = False
        self.__class__.log_event_override = False
        self.__class__.dcs_override = False
        self.__class__.get_id_lists_override = False

    def test_override_api_only(self, mock_request):
        options = StatsigOptions(api=_api_stubs["api"].host)
        statsig.initialize("secret-test", options)
        statsig.check_gate(StatsigUser("test_user"), "always_on_gate")
        statsig.flush()
        self.assertTrue(self.api_override)
        self.assertFalse(self.log_event_override)
        self.assertFalse(self.dcs_override)
        statsig.shutdown()

    def test_override_log_event_only(self, mock_request):
        options = StatsigOptions(api_for_log_event=_api_stubs["log_event"].host)
        statsig.initialize("secret-test", options)
        statsig.check_gate(StatsigUser("test_user"), "always_on_gate")
        statsig.flush()
        self.assertFalse(self.api_override)
        self.assertTrue(self.log_event_override)
        self.assertFalse(self.dcs_override)
        statsig.shutdown()

    def test_override_dcs_only(self, mock_request):
        options = StatsigOptions(
            api_for_download_config_specs=_api_stubs
            ["download_config_specs"].host)
        statsig.initialize("secret-test", options)
        statsig.check_gate(StatsigUser("test_user"), "always_on_gate")
        statsig.flush()
        self.assertFalse(self.api_override)
        self.assertFalse(self.log_event_override)
        self.assertTrue(self.dcs_override)
        statsig.shutdown()

    def test_override_all(self, mock_request):
        options = StatsigOptions(
            api=_api_stubs["api"].host,
            api_for_log_event=_api_stubs["log_event"].host,
            api_for_download_config_specs=_api_stubs["download_config_specs"].host,
            api_for_get_id_lists=_api_stubs["get_id_lists"].host
        )
        statsig.initialize("secret-test", options)
        statsig.check_gate(StatsigUser("test_user"), "always_on_gate")
        statsig.flush()
        self.assertFalse(self.api_override)
        self.assertTrue(self.log_event_override)
        self.assertTrue(self.dcs_override)
        self.assertTrue(self.get_id_lists_override)
        statsig.shutdown()
