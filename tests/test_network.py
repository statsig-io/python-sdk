import unittest
from unittest.mock import MagicMock, patch
from urllib.parse import urlparse
from uuid import uuid4

from statsig import StatsigOptions
from statsig import globals
from statsig.diagnostics import Diagnostics
from statsig.http_worker import HttpWorker
from statsig.interface_network import NetworkEndpoint, NetworkProtocol
from statsig.request_result import RequestResult
from statsig.statsig_context import InitContext
from statsig.statsig_error_boundary import _StatsigErrorBoundary
from statsig.statsig_event import StatsigEvent
from statsig.statsig_metadata import _StatsigMetadata
from statsig.statsig_network import _StatsigNetwork
from statsig.statsig_options import ProxyConfig
from statsig.spec_updater import SpecUpdater
from statsig.statsig_user import StatsigUser

SAMPLE_ID_LIST_DOWNLOAD_URL = (
    "https://fake-id-list-host/v1/download_id_list_file/"
    "1i4Go90gg3pfnFYbKIqOXM%2F1BksscSGeQotm9oHQXiF1o"
    "?sv=2020-10-02&se=2026-02-27T17%3A49%3A49Z&sr=b&sp=r"
    "&sig=G%2BEmgpIiHgmanxPWSWdpLu3dUJ68HGb7vXNv0y28y4c%3D&k=secret-test"
)


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
        self.assertEqual(kwargs["context"], "background_sync")

    def test_initialize_network_latency_metric_includes_initialize_context(self):
        self.net._HttpWorker__api_for_get_id_lists = "https://api.statsigcdn.com/v1/"

        def fake_request(_method, _url, *_args, **_kwargs):
            return RequestResult(data={}, status_code=200, success=True, error=None)

        with patch.object(self.net, "_run_request_with_strict_timeout", side_effect=fake_request), patch.object(
            globals.logger, "log_network_request_latency"
        ) as latency_mock:
            self.net.get_id_lists(lambda *_: None, request_context="initialize")

        latency_mock.assert_called_once()
        kwargs = latency_mock.call_args.kwargs
        self.assertEqual(kwargs["context"], "initialize")

    def test_id_list_network_latency_metric_includes_file_id_tag(self):
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
        self.assertEqual(kwargs["context"], "background_sync")
        self.assertEqual(kwargs["extra_tags"], {"id_list_file_id": "4PKKLINp6EZW3DNQ73sCxY"})

    def test_log_event_does_not_emit_network_latency(self):
        def fake_request(_method, _url, *_args, **_kwargs):
            return RequestResult(data={}, status_code=200, success=True, error=None)

        with patch.object(self.net, "_run_request_with_strict_timeout", side_effect=fake_request), patch.object(
            globals.logger, "log_network_request_latency"
        ) as latency_mock:
            self.net.log_events({"events": []})

        latency_mock.assert_not_called()

    def test_id_list_uses_sfp_download_endpoint_when_configured(self):
        captured_url = {}
        net = HttpWorker(
            "secret-test",
            StatsigOptions(
                disable_diagnostics=True,
                proxy_configs={
                    NetworkEndpoint.DOWNLOAD_ID_LIST_FILE: ProxyConfig(
                        proxy_address="http://test-proxy-id-list",
                        protocol=NetworkProtocol.HTTP,
                    )
                },
            ),
            _StatsigMetadata.get(),
            _StatsigErrorBoundary(),
            Diagnostics(),
            InitContext(),
        )

        def fake_request(_method, _url, *_args, **_kwargs):
            captured_url["url"] = _url
            return RequestResult(
                data={},
                status_code=200,
                success=True,
                error=None,
                text="+1\r",
                headers={"content-length": "3"},
            )

        with patch.object(net, "_run_request_with_strict_timeout", side_effect=fake_request):
            net.get_id_list(lambda *_: None, SAMPLE_ID_LIST_DOWNLOAD_URL, headers={})

        self.assertEqual(
            captured_url.get("url"),
            SAMPLE_ID_LIST_DOWNLOAD_URL.replace(
                "https://fake-id-list-host",
                "http://test-proxy-id-list",
                1,
            ),
        )


class TestStatsigNetwork(unittest.TestCase):

    def test_get_id_list_prefers_download_id_list_file_worker(self):
        metadata = _StatsigMetadata.get()
        options = StatsigOptions(
            disable_diagnostics=True,
            proxy_configs={
                NetworkEndpoint.DOWNLOAD_ID_LIST_FILE: ProxyConfig(
                    proxy_address="http://test-proxy-id-list",
                    protocol=NetworkProtocol.HTTP,
                )
            },
        )
        network = _StatsigNetwork(
            "secret-test",
            options,
            metadata,
            _StatsigErrorBoundary(),
            Diagnostics(),
            None,
            InitContext(),
        )

        default_worker = HttpWorker(
            "secret-test",
            StatsigOptions(disable_diagnostics=True),
            metadata,
            _StatsigErrorBoundary(),
            Diagnostics(),
            InitContext(),
        )
        download_worker = HttpWorker(
            "secret-test",
            StatsigOptions(disable_diagnostics=True),
            metadata,
            _StatsigErrorBoundary(),
            Diagnostics(),
            InitContext(),
        )
        default_worker.get_id_list = MagicMock()
        download_worker.get_id_list = MagicMock()

        network.http_worker = default_worker
        network.id_list_file_download_worker = download_worker
        network.get_id_list(
            lambda *_: None,
            SAMPLE_ID_LIST_DOWNLOAD_URL,
            {},
            id_list_file_id="file_id_1",
        )

        download_worker.get_id_list.assert_called_once()
        default_worker.get_id_list.assert_not_called()


class TestSpecUpdater(unittest.TestCase):

    class _TestDataStore:
        def __init__(self, data=None):
            self.data = data or {}

        def get(self, key: str):
            return self.data.get(key)

        def set(self, key: str, value: str):
            self.data[key] = value

    def test_download_single_id_list_sends_id_list_file_size_header(self):
        network = MagicMock()
        network.get_id_list.side_effect = lambda on_complete, *_args, **_kwargs: on_complete(
            RequestResult(
                data={},
                status_code=200,
                success=True,
                error=None,
                text="+abc\r",
                headers={"content-length": "5"},
            )
        )
        updater = SpecUpdater(
            network,
            None,
            StatsigOptions(disable_diagnostics=True),
            Diagnostics(),
            "secret-test",
            _StatsigErrorBoundary(),
            _StatsigMetadata.get(),
            MagicMock(),
            InitContext(),
        )

        local_list = {"ids": set(), "fileID": "file_id_1", "size": 123}
        all_lists = {}
        updater.download_single_id_list(
            SAMPLE_ID_LIST_DOWNLOAD_URL,
            "list_name",
            local_list,
            all_lists,
            0,
        )

        network.get_id_list.assert_called_once()
        headers = network.get_id_list.call_args.kwargs["headers"]
        self.assertEqual(headers["Range"], "bytes=0-")
        self.assertEqual(headers["statsig-id-list-file-size"], "123")

    def test_download_single_id_list_uses_data_store_with_file_id_key(self):
        data_store = self._TestDataStore({
            "/v1/download_id_list_file/file_id_1": "+1\r-1\r+2\r",
        })
        network = MagicMock()
        updater = SpecUpdater(
            network,
            data_store,
            StatsigOptions(disable_diagnostics=True, data_store=data_store),
            Diagnostics(),
            "secret-test",
            _StatsigErrorBoundary(),
            _StatsigMetadata.get(),
            MagicMock(),
            InitContext(),
        )

        local_list = {
            "ids": set(["1"]),
            "fileID": "file_id_1",
            "size": 9,
        }
        all_lists = {}

        success = updater.download_single_id_list(
            "https://fake-id-list-host/list_1",
            "list_name",
            local_list,
            all_lists,
            3,
        )

        self.assertTrue(success)
        network.get_id_list.assert_not_called()
        self.assertEqual(all_lists["list_name"]["ids"], set(["2"]))
        self.assertEqual(all_lists["list_name"]["readBytes"], 9)

    def test_download_single_id_list_appends_network_suffix_to_data_store(self):
        data_store_key = urlparse(SAMPLE_ID_LIST_DOWNLOAD_URL).path
        data_store = self._TestDataStore()
        network = MagicMock()
        responses = [
            RequestResult(
                data={},
                status_code=200,
                success=True,
                error=None,
                text="+1\r",
                headers={"content-length": "3"},
            ),
            RequestResult(
                data={},
                status_code=200,
                success=True,
                error=None,
                text="-1\r+2\r",
                headers={"content-length": "6"},
            ),
        ]
        network.get_id_list.side_effect = lambda on_complete, *_args, **_kwargs: on_complete(
            responses.pop(0)
        )
        updater = SpecUpdater(
            network,
            data_store,
            StatsigOptions(disable_diagnostics=True, data_store=data_store),
            Diagnostics(),
            "secret-test",
            _StatsigErrorBoundary(),
            _StatsigMetadata.get(),
            MagicMock(),
            InitContext(),
        )

        local_list = {"ids": set(), "fileID": "file_id_1", "size": 3}
        all_lists = {}
        self.assertTrue(
            updater.download_single_id_list(
                SAMPLE_ID_LIST_DOWNLOAD_URL,
                "list_name",
                local_list,
                all_lists,
                0,
            )
        )
        self.assertEqual(data_store.data[data_store_key], "+1\r")

        local_list["size"] = 9
        self.assertTrue(
            updater.download_single_id_list(
                SAMPLE_ID_LIST_DOWNLOAD_URL,
                "list_name",
                local_list,
                all_lists,
                3,
            )
        )
        self.assertEqual(data_store.data[data_store_key], "+1\r-1\r+2\r")
        self.assertEqual(all_lists["list_name"]["ids"], set(["2"]))
        self.assertEqual(all_lists["list_name"]["readBytes"], 9)
