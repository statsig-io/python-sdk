import unittest
from unittest.mock import patch
from uuid import uuid4

from statsig import StatsigOptions
from statsig import globals
from statsig.diagnostics import Diagnostics
from statsig.http_worker import HttpWorker
from statsig.request_result import RequestResult
from statsig.statsig_context import InitContext
from statsig.statsig_error_boundary import _StatsigErrorBoundary
from statsig.statsig_event import StatsigEvent
from statsig.statsig_metadata import _StatsigMetadata
from statsig.statsig_user import StatsigUser


class TestNetworkHTTPWorker(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # This test logspews expected errors, but the test itself should pass
        globals.logger._disabled = False
        metadata = _StatsigMetadata.get()
        cls.net = HttpWorker("secret-test", StatsigOptions(disable_diagnostics=True), metadata,
                             _StatsigErrorBoundary(), Diagnostics(), InitContext())
        cls.net._raise_on_error = True

    @classmethod
    def tearDownClass(cls):
        globals.logger._disabled = True

    def test_invalid_user(self):
        user = StatsigUser(user_id="123", custom={'field': uuid4()})
        event = StatsigEvent(user, "test_event")
        # request fails due to json serialization of user
        self.assertRaises(
            TypeError,
            self.net.log_events,
            {
                'events': [
                    event.to_dict()
                ],
            },
            True,
        )

    def test_invalid_metadata(self):
        user = StatsigUser(user_id="123", )
        event = StatsigEvent(user, "test_event", None, {'field': uuid4()})
        # request fails due to json serialization of event
        self.assertRaises(
            TypeError,
            self.net.log_events,
            {
                'events': [
                    event.to_dict()
                ],
            },
            True,
        )

    def test_invalid_post(self):
        user = StatsigUser(user_id="123", )
        event = StatsigEvent(user, "test_event", None, {'field': uuid4()})
        # request fails due to json serialization of event
        self.assertRaises(
            TypeError,
            self.net._post_request,
            "http://statsigapi.net/v1/log_event3",
            None,
            {
                'events': [
                    event.to_dict()
                ],
            },
            True,
        )
        
    # Explicitly set Connection: close header to avoid peer connection issues in some environments
    def test_request_session_connection_header(self):
        request_session = self.net._HttpWorker__request_session
        self.assertEqual(request_session.headers.get("Connection"), "close")

    def test_dcs_service_header_sent_for_forward_proxy_url(self):
        captured_headers = {}
        self.net._HttpWorker__service_name = "unit-test-service"
        self.net._HttpWorker__api_for_download_config_specs = "http://test/statsig-foward-proxy/"

        def fake_request(_method, _url, headers, *_args, **_kwargs):
            captured_headers.update(headers or {})
            return RequestResult(data={}, status_code=200, success=True, error=None)

        with patch.object(self.net, "_run_request_with_strict_timeout", side_effect=fake_request):
            self.net.get_dcs(lambda *_: None)

        self.assertEqual(captured_headers.get("x-request-service"), "unit-test-service")

    def test_dcs_service_header_sent_without_forward_proxy_url(self):
        captured_headers = {}
        self.net._HttpWorker__service_name = "unit-test-service"
        self.net._HttpWorker__api_for_download_config_specs = "http://test/no-forward-proxy/"

        def fake_request(_method, _url, headers, *_args, **_kwargs):
            captured_headers.update(headers or {})
            return RequestResult(data={}, status_code=200, success=True, error=None)

        with patch.object(self.net, "_run_request_with_strict_timeout", side_effect=fake_request):
            self.net.get_dcs(lambda *_: None)

        self.assertEqual(captured_headers.get("x-request-service"), "unit-test-service")

    def test_id_lists_service_header_sent_for_forward_proxy_url(self):
        captured_headers = {}
        self.net._HttpWorker__service_name = "unit-test-service"
        self.net._HttpWorker__api_for_get_id_lists = "http://test/statsig-foward-proxy/"

        def fake_request(_method, _url, headers, *_args, **_kwargs):
            captured_headers.update(headers or {})
            return RequestResult(data={}, status_code=200, success=True, error=None)

        with patch.object(self.net, "_run_request_with_strict_timeout", side_effect=fake_request):
            self.net.get_id_lists(lambda *_: None)

        self.assertEqual(captured_headers.get("x-request-service"), "unit-test-service")

    def test_id_lists_service_header_sent_without_forward_proxy_url(self):
        captured_headers = {}
        self.net._HttpWorker__service_name = "unit-test-service"
        self.net._HttpWorker__api_for_get_id_lists = "http://test/no-forward-proxy/"

        def fake_request(_method, _url, headers, *_args, **_kwargs):
            captured_headers.update(headers or {})
            return RequestResult(data={}, status_code=200, success=True, error=None)

        with patch.object(self.net, "_run_request_with_strict_timeout", side_effect=fake_request):
            self.net.get_id_lists(lambda *_: None)

        self.assertEqual(captured_headers.get("x-request-service"), "unit-test-service")

    def test_id_list_service_header_sent_for_forward_proxy_url(self):
        captured_headers = {}
        self.net._HttpWorker__service_name = "unit-test-service"

        def fake_request(_method, _url, headers, *_args, **_kwargs):
            captured_headers.update(headers or {})
            return RequestResult(data={}, status_code=200, success=True, error=None, text="+1\r")

        with patch.object(self.net, "_run_request_with_strict_timeout", side_effect=fake_request):
            self.net.get_id_list(lambda *_: None, "http://test/statsig-foward-proxy/list_1", headers={})

        self.assertEqual(captured_headers.get("x-request-service"), "unit-test-service")

    def test_id_list_service_header_sent_without_forward_proxy_url(self):
        captured_headers = {}
        self.net._HttpWorker__service_name = "unit-test-service"

        def fake_request(_method, _url, headers, *_args, **_kwargs):
            captured_headers.update(headers or {})
            return RequestResult(data={}, status_code=200, success=True, error=None, text="+1\r")

        with patch.object(self.net, "_run_request_with_strict_timeout", side_effect=fake_request):
            self.net.get_id_list(lambda *_: None, "http://test/no-forward-proxy/list_1", headers={})

        self.assertEqual(captured_headers.get("x-request-service"), "unit-test-service")

    def test_network_latency_metric_includes_required_tags(self):
        self.net._HttpWorker__api_for_get_id_lists = "https://api.statsigcdn.com/v1/"

        def fake_request(_method, _url, *_args, **_kwargs):
            return RequestResult(data={}, status_code=200, success=True, error=None)

        with patch.object(self.net, "_run_request_with_strict_timeout", side_effect=fake_request), patch.object(
            globals.logger, "log_network_request_latency"
        ) as latency_mock:
            self.net.get_id_lists(lambda *_: None)

        latency_mock.assert_called_once()
        kwargs = latency_mock.call_args.kwargs
        self.assertEqual(kwargs["status_code"], 200)
        self.assertEqual(kwargs["source_service"], "https://api.statsigcdn.com")
        self.assertEqual(kwargs["partial_sdk_key"], "secret-test")
        self.assertEqual(kwargs["request_path"], "/v1/get_id_lists")

    def test_id_list_network_latency_metric_includes_file_id_tag(self):
        self.net._HttpWorker__api_for_get_id_lists = "https://api.statsigcdn.com/v1/"

        def fake_request(_method, _url, *_args, **_kwargs):
            return RequestResult(
                data={},
                status_code=200,
                success=True,
                error=None,
                text="+1\r",
                headers={"content-length": "3"},
            )

        with patch.object(self.net, "_run_request_with_strict_timeout", side_effect=fake_request), patch.object(
            globals.logger, "log_network_request_latency"
        ) as latency_mock:
            self.net.get_id_list(
                lambda *_: None,
                "https://api.statsigcdn.com/v1/download_id_list_file/foo",
                headers={},
                id_list_file_id="4PKKLINp6EZW3DNQ73sCxY",
            )

        latency_mock.assert_called_once()
        kwargs = latency_mock.call_args.kwargs
        self.assertEqual(kwargs["status_code"], 200)
        self.assertEqual(kwargs["source_service"], "https://api.statsigcdn.com")
        self.assertEqual(kwargs["request_path"], "/v1/download_id_list_file")
        self.assertEqual(kwargs["extra_tags"], {"id_list_file_id": "4PKKLINp6EZW3DNQ73sCxY"})

    def test_id_list_download_uses_get_id_lists_proxy_when_configured(self):
        captured_urls = []
        self.net._HttpWorker__api_for_get_id_lists = "http://sfp-proxy.local/v1/"

        def fake_request(_method, url, *_args, **_kwargs):
            captured_urls.append(url)
            return RequestResult(
                data={},
                status_code=200,
                success=True,
                error=None,
                text="+1\r",
                headers={"content-length": "3"},
            )

        with patch.object(self.net, "_run_request_with_strict_timeout", side_effect=fake_request):
            self.net.get_id_list(
                lambda *_: None,
                "https://api.statsigcdn.com/v1/download_id_list_file/foo%2Fbar?sv=2020-10-02&sig=abc&k=secret-test",
                headers={},
            )

        self.assertEqual(
            captured_urls,
            ["http://sfp-proxy.local/v1/download_id_list_file/foo%2Fbar?sv=2020-10-02&sig=abc&k=secret-test"],
        )

    def test_id_list_download_falls_back_to_cdn_when_proxy_fails(self):
        captured_urls = []
        self.net._HttpWorker__api_for_get_id_lists = "http://sfp-proxy.local/v1/"
        cdn_url = (
            "https://api.statsigcdn.com/v1/download_id_list_file/foo"
            "?sv=2020-10-02&sig=abc&k=secret-test"
        )
        proxy_url = "http://sfp-proxy.local/v1/download_id_list_file/foo?sv=2020-10-02&sig=abc&k=secret-test"

        def fake_request(_method, url, *_args, **_kwargs):
            captured_urls.append(url)
            if url == proxy_url:
                return RequestResult(data=None, status_code=502, success=False, error=None)
            return RequestResult(
                data={},
                status_code=200,
                success=True,
                error=None,
                text="+1\r",
                headers={"content-length": "3"},
            )

        with patch.object(self.net, "_run_request_with_strict_timeout", side_effect=fake_request):
            self.net.get_id_list(lambda *_: None, cdn_url, headers={})

        self.assertEqual(captured_urls, [proxy_url, cdn_url])

    def test_log_event_does_not_emit_network_latency(self):
        def fake_request(_method, _url, *_args, **_kwargs):
            return RequestResult(data={}, status_code=200, success=True, error=None)

        with patch.object(self.net, "_run_request_with_strict_timeout", side_effect=fake_request), patch.object(
            globals.logger, "log_network_request_latency"
        ) as latency_mock:
            self.net.log_events({"events": []})

        latency_mock.assert_not_called()
