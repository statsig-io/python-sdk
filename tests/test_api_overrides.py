import json
import os
import unittest
from unittest.mock import patch
from urllib.parse import ParseResult, urlparse

from statsig import statsig, StatsigOptions, StatsigUser
from tests.network_stub import NetworkStub

_api_stubs = {
    "download_config_specs": NetworkStub("http://test-dcs"),
    "log_event": NetworkStub("http://test-log-event"),
    "api": NetworkStub("http://test-api")
}

with open(os.path.join(os.path.abspath(os.path.dirname(__file__)), '../testdata/download_config_specs.json')) as r:
    CONFIG_SPECS_RESPONSE = r.read()


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

        api_stub = _api_stubs["api"]
        api_stub.stub_request_with_value("download_config_specs/.*", 500, {})
        dcs_stub = _api_stubs["download_config_specs"]
        dcs_stub.stub_request_with_value("download_config_specs/.*", 200, json.loads(CONFIG_SPECS_RESPONSE))
        log_event_stub = _api_stubs["log_event"]
        log_event_stub.stub_request_with_value("download_config_specs/.*", 500, {})

        def on_log(url, **kwargs):
            if url.hostname == "test-api":
                cls.api_override = True
            if url.hostname == "test-log-event":
                cls.log_event_override = True
            if url.hostname == "test-dcs":
                cls.dcs_override = True

        api_stub.stub_request_with_function("log_event", 202, on_log)
        dcs_stub.stub_request_with_function("log_event", 202, on_log)
        log_event_stub.stub_request_with_function("log_event", 202, on_log)
    @classmethod
    def tearDownClass(cls):
        cls.api_override = False
        cls.log_event_override = False
        cls.dcs_override = False
        statsig.shutdown()

    def setUp(self):
        # Reset class variables before each test
        self.__class__.api_override = False
        self.__class__.log_event_override = False
        self.__class__.dcs_override = False

    def test_override_api_only(self, mock_request):
        # api override has no dcs response, api_override should have been called
        options = StatsigOptions(api=_api_stubs["api"].host)
        statsig.initialize("secret-test", options)
        self.assertFalse(statsig.check_gate(StatsigUser("test_user"), "always_on_gate"))
        statsig.flush()
        self.assertTrue(self.api_override)
        self.assertFalse(self.log_event_override)
        self.assertFalse(self.dcs_override)
        statsig.shutdown()


    def test_override_log_event_only(self, mock_request):
        # log_event override has no dcs response, log_event_override should have been called
        options = StatsigOptions(api_for_log_event=_api_stubs["log_event"].host)
        statsig.initialize("secret-test", options)
        self.assertFalse(statsig.check_gate(StatsigUser("test_user"), "always_on_gate"))
        statsig.flush()
        self.assertFalse(self.api_override)
        self.assertTrue(self.log_event_override)
        self.assertFalse(self.dcs_override)
        statsig.shutdown()


    def test_override_dcs_only(self, mock_request):
        # dcs override has dcs response, dcs_override should NOT have been called for log_event
        options = StatsigOptions(api_for_download_config_specs=_api_stubs["download_config_specs"].host)
        statsig.initialize("secret-test", options)
        self.assertTrue(statsig.check_gate(StatsigUser("test_user"), "always_on_gate"))
        statsig.flush()
        self.assertFalse(self.api_override)
        self.assertFalse(self.log_event_override)
        self.assertFalse(self.dcs_override)
        statsig.shutdown()


    def test_override_all(self, mock_request):
        options = StatsigOptions(
            api=_api_stubs["api"].host,
            api_for_log_event=_api_stubs["log_event"].host,
            api_for_download_config_specs=_api_stubs["download_config_specs"].host
        )
        statsig.initialize("secret-test", options)
        self.assertTrue(statsig.check_gate(StatsigUser("test_user"), "always_on_gate"))
        statsig.flush()
        self.assertFalse(self.api_override)
        self.assertTrue(self.log_event_override)
        self.assertFalse(self.dcs_override)
        statsig.shutdown()
