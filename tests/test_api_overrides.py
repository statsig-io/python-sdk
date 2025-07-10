import json
import os
import unittest
from unittest.mock import patch
from urllib.parse import urlparse

from network_stub import NetworkStub
from statsig import statsig, StatsigOptions, StatsigUser
from statsig.interface_network import NetworkEndpoint, NetworkProtocol
from statsig.statsig_options import ProxyConfig

_api_stubs = {
    "download_config_specs": NetworkStub("http://test-dcs"),
    "get_id_lists": NetworkStub("http://test-get-id-lists"),
    "log_event": NetworkStub("http://test-log-event"),
    "api": NetworkStub("http://test-api"),
    "dcs_proxy": NetworkStub("http://test-proxy-dcs"),
    "id_list_proxy": NetworkStub("http://test-proxy-id-list"),
    "log_event_proxy": NetworkStub("http://test-proxy-log-event"),
}

with open(
        os.path.join(
            os.path.abspath(os.path.dirname(__file__)),
            "../testdata/download_config_specs.json",
        )
) as r:
    CONFIG_SPECS_RESPONSE = r.read()


def mock_apis(*args, **kwargs):
    url = urlparse(args[1])
    for stub in _api_stubs.values():
        if stub.host in url.scheme + "://" + url.hostname or url.scheme + "://" + url.hostname in stub.host:
            return stub.mock(*args, **kwargs)


@patch('requests.Session.request', side_effect=mock_apis)
class TestApiOverrides(unittest.TestCase):
    @classmethod
    @patch('requests.Session.request', side_effect=mock_apis)
    def setUpClass(cls, mock_request):
        cls.api_override = False
        cls.log_event_override = False
        cls.dcs_override = False
        cls.get_id_lists_override = False
        cls.dcs_proxy_override = False
        cls.id_list_proxy_override = False
        cls.log_event_proxy_override = False

        def on_log(url, **kwargs):
            if url.hostname == "test-api":
                cls.api_override = True
            if url.hostname == "test-log-event":
                cls.log_event_override = True
            if url.hostname == "test-dcs":
                cls.dcs_override = True
                return json.loads(CONFIG_SPECS_RESPONSE)
            if url.hostname == "test-get-id-lists":
                cls.get_id_lists_override = True
                return {}
            if url.hostname == "test-proxy-dcs":
                cls.dcs_proxy_override = True
                return json.loads(CONFIG_SPECS_RESPONSE)
            if url.hostname == "test-proxy-id-list":
                cls.id_list_proxy_override = True
                return {}
            if url.hostname == "test-proxy-log-event":
                cls.log_event_proxy_override = True

        _api_stubs["api"].stub_request_with_function(".*", 202, on_log)
        _api_stubs["download_config_specs"].stub_request_with_function(".*", 202, on_log)
        _api_stubs["get_id_lists"].stub_request_with_function(".*", 200, on_log)
        _api_stubs["log_event"].stub_request_with_function(".*", 202, on_log)
        _api_stubs["dcs_proxy"].stub_request_with_function(".*", 202, on_log)
        _api_stubs["id_list_proxy"].stub_request_with_function(".*", 200, on_log)
        _api_stubs["log_event_proxy"].stub_request_with_function(".*", 202, on_log)

    @classmethod
    def tearDownClass(cls):
        cls.api_override = False
        cls.log_event_override = False
        cls.dcs_override = False
        cls.get_id_lists_override = False
        cls.dcs_proxy_override = False
        cls.id_list_proxy_override = False
        cls.log_event_proxy_override = False
        statsig.shutdown()

    def setUp(self):
        # Reset class variables before each test
        self.__class__.api_override = False
        self.__class__.log_event_override = False
        self.__class__.dcs_override = False
        self.__class__.get_id_lists_override = False
        self.__class__.dcs_proxy_override = False
        self.__class__.id_list_proxy_override = False
        self.__class__.log_event_proxy_override = False

    def test_override_api_only(self, mock_request):
        options = StatsigOptions(api=_api_stubs["api"].host)
        init_details = statsig.initialize("secret-test", options)
        statsig.check_gate(StatsigUser("test_user"), "always_on_gate")
        statsig.flush()
        self.assertTrue(self.api_override)
        self.assertFalse(self.log_event_override)
        self.assertFalse(self.dcs_override)
        statsig.shutdown()
        self.assertTrue(_api_stubs["api"].host in init_details.init_source_api)

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
        init_details = statsig.initialize("secret-test", options)
        statsig.check_gate(StatsigUser("test_user"), "always_on_gate")
        statsig.flush()
        self.assertFalse(self.api_override)
        self.assertFalse(self.log_event_override)
        self.assertTrue(self.dcs_override)
        statsig.shutdown()
        self.assertTrue(_api_stubs["download_config_specs"].host in init_details.init_source_api)

    def test_override_all(self, mock_request):
        options = StatsigOptions(
            api=_api_stubs["api"].host,
            api_for_log_event=_api_stubs["log_event"].host,
            api_for_download_config_specs=_api_stubs["download_config_specs"].host,
            api_for_get_id_lists=_api_stubs["get_id_lists"].host
        )
        init_details = statsig.initialize("secret-test", options)
        statsig.check_gate(StatsigUser("test_user"), "always_on_gate")
        statsig.flush()
        self.assertFalse(self.api_override)
        self.assertTrue(self.log_event_override)
        self.assertTrue(self.dcs_override)
        self.assertTrue(self.get_id_lists_override)
        statsig.shutdown()
        self.assertTrue(_api_stubs["download_config_specs"].host in init_details.init_source_api)

    def test_dcs_proxy_address_override(self, mock_request):
        options = StatsigOptions(
            proxy_configs={
                NetworkEndpoint.DOWNLOAD_CONFIG_SPECS: ProxyConfig(
                    proxy_address=_api_stubs["dcs_proxy"].host,
                    protocol=NetworkProtocol.HTTP
                )
            })
        init_details = statsig.initialize("secret-test", options)
        self.assertFalse(self.dcs_override)
        self.assertTrue(self.dcs_proxy_override)
        statsig.shutdown()
        self.assertTrue(_api_stubs["dcs_proxy"].host in init_details.init_source_api)

    def test_id_list_proxy_address_override(self, mock_request):
        options = StatsigOptions(
            proxy_configs={
                NetworkEndpoint.GET_ID_LISTS: ProxyConfig(
                    proxy_address=_api_stubs["id_list_proxy"].host,
                    protocol=NetworkProtocol.HTTP
                )
            })
        statsig.initialize("secret-test", options)
        self.assertFalse(self.get_id_lists_override)
        self.assertTrue(self.id_list_proxy_override)
        statsig.shutdown()

    def test_log_event_proxy_address_override(self, mock_request):
        options = StatsigOptions(
            proxy_configs={
                NetworkEndpoint.LOG_EVENT: ProxyConfig(
                    proxy_address=_api_stubs["log_event_proxy"].host,
                    protocol=NetworkProtocol.HTTP
                )
            })
        statsig.initialize("secret-test", options)
        statsig.check_gate(StatsigUser("test_user"), "always_on_gate")
        statsig.flush()
        self.assertFalse(self.log_event_override)
        self.assertTrue(self.log_event_proxy_override)
        statsig.shutdown()

    def test_all_proxy_override(self, mock_request):
        options = StatsigOptions(
            api=_api_stubs["api"].host,
            api_for_log_event=_api_stubs["log_event"].host,
            api_for_download_config_specs=_api_stubs["download_config_specs"].host,
            api_for_get_id_lists=_api_stubs["get_id_lists"].host,
            proxy_configs={
                NetworkEndpoint.DOWNLOAD_CONFIG_SPECS: ProxyConfig(
                    proxy_address=_api_stubs["dcs_proxy"].host,
                    protocol=NetworkProtocol.HTTP
                ),
                NetworkEndpoint.GET_ID_LISTS: ProxyConfig(
                    proxy_address=_api_stubs["id_list_proxy"].host,
                    protocol=NetworkProtocol.HTTP
                ),
                NetworkEndpoint.LOG_EVENT: ProxyConfig(
                    proxy_address=_api_stubs["log_event_proxy"].host,
                    protocol=NetworkProtocol.HTTP
                )
            })
        init_details = statsig.initialize("secret-test", options)
        statsig.check_gate(StatsigUser("test_user"), "always_on_gate")
        statsig.flush()
        self.assertFalse(self.api_override)
        self.assertFalse(self.log_event_override)
        self.assertFalse(self.dcs_override)
        self.assertTrue(self.dcs_proxy_override)
        self.assertTrue(self.id_list_proxy_override)
        self.assertTrue(self.log_event_proxy_override)
        statsig.shutdown()
        self.assertTrue(_api_stubs["dcs_proxy"].host in init_details.init_source_api)
