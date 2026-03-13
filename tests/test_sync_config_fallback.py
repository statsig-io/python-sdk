import json
import os
import threading
import time
import unittest
from unittest.mock import Mock, patch

from network_stub import NetworkStub
from statsig import StatsigOptions, statsig, StatsigUser, IDataStore
from statsig.evaluation_details import EvaluationDetails
from statsig.statsig_options import DataSource
from statsig.spec_updater import SpecUpdater

_network_stub = NetworkStub("http://test-sync-config-fallback", mock_statsig_api=True)
with open(os.path.join(os.path.abspath(os.path.dirname(__file__)), '../testdata/download_config_specs.json')) as r:
    CONFIG_SPECS_RESPONSE = r.read()
PARSED_CONFIG_SPEC = json.loads(CONFIG_SPECS_RESPONSE)

UPDATED_TIME_CONFIG_SPEC = PARSED_CONFIG_SPEC.copy()
UPDATED_TIME_CONFIG_SPEC['time'] = 1631638014821


@patch('requests.Session.request', side_effect=_network_stub.mock)
class TestSyncConfigFallback(unittest.TestCase):
    @classmethod
    @patch('requests.Session.request', side_effect=_network_stub.mock)
    def setUpClass(cls, mock_proxy):
        cls.dcs_called = False
        cls.statsig_dcs_called = False
        cls.status_code = 200

        SpecUpdater.STATSIG_NETWORK_FALLBACK_THRESHOLD = 1

        cls.test_user = StatsigUser("123", email="testuser@statsig.com")

    def setUp(self):
        self.__class__.dcs_called = False
        self.__class__.statsig_dcs_called = False
        self.__class__.status_code = 200

        def statsig_dcs_cb(url, **kwargs):
            self.__class__.statsig_dcs_called = True
            return PARSED_CONFIG_SPEC

        _network_stub.stub_request_with_value("get_id_lists", 200, {})
        _network_stub.stub_statsig_api_request_with_function(
            "download_config_specs/.*", 200, statsig_dcs_cb)

    def stub_network(self, status_code, incomplete_read=False, gzip=False):
        self.__class__.status_code = status_code

        def cb(url, **kwargs):
            self.__class__.dcs_called = True
            if self.__class__.status_code == 200:
                return PARSED_CONFIG_SPEC
            if self.__class__.status_code == 202:  # just for testing ok status code but invalid json
                return "{jiBbRIsh;"
            if self.__class__.status_code == 400:
                return "{}"
            if self.__class__.status_code == 500:
                raise Exception("Internal Server Error")

        options = {}
        if incomplete_read:
            options["incompleteRead"] = True
        headers = {}
        if gzip:
            headers["Content-Encoding"] = "gzip"

        _network_stub.stub_request_with_function(
            "download_config_specs/.*", self.__class__.status_code, cb, headers=headers, options=options)

    def tearDown(self):
        statsig.shutdown()
        _network_stub.reset()

    def test_default_sync_success(self, request_mock):
        self.stub_network(200)
        options = StatsigOptions(api=_network_stub.host, fallback_to_statsig_api=True, rulesets_sync_interval=1)
        init_detail = statsig.initialize("secret-key", options)
        self.assertIsNone(init_detail.error)
        gate = statsig.get_feature_gate(self.test_user, "always_on_gate")
        eval_detail: EvaluationDetails = gate.get_evaluation_details()
        self.assertEqual(eval_detail.source, DataSource.NETWORK)
        self.assertEqual(eval_detail.config_sync_time, 1631638014811)
        time.sleep(1.1)
        self.assertFalse(self.__class__.statsig_dcs_called)

    def test_fallback_when_out_of_sync(self, request_mock):
        self.stub_network(200)
        options = StatsigOptions(api=_network_stub.host, fallback_to_statsig_api=True,
                                 rulesets_sync_interval=1, out_of_sync_threshold_in_s=0.5)
        statsig.initialize("secret-key", options)
        gate = statsig.get_feature_gate(self.test_user, "always_on_gate")
        eval_detail: EvaluationDetails = gate.get_evaluation_details()
        self.assertEqual(eval_detail.source, DataSource.NETWORK)
        self.assertEqual(eval_detail.config_sync_time, 1631638014811)
        time.sleep(1.1)
        self.assertTrue(self.__class__.statsig_dcs_called)

    def test_no_fallback_when_not_out_of_sync(self, request_mock):
        self.stub_network(200)
        options = StatsigOptions(api=_network_stub.host, fallback_to_statsig_api=True,
                                 rulesets_sync_interval=1, out_of_sync_threshold_in_s=4e10)
        statsig.initialize("secret-key", options)
        gate = statsig.get_feature_gate(self.test_user, "always_on_gate")
        eval_detail: EvaluationDetails = gate.get_evaluation_details()
        self.assertEqual(eval_detail.source, DataSource.NETWORK)
        self.assertEqual(eval_detail.config_sync_time, 1631638014811)
        time.sleep(1.1)
        self.assertFalse(self.__class__.statsig_dcs_called)

    def test_sync_strategies_use_network_before_statsig_network_with_datastore(self, request_mock):
        class _TestAdapter(IDataStore):
            def should_be_used_for_querying_updates(self, key: str) -> bool:
                return True

        options = StatsigOptions(data_store=_TestAdapter(), fallback_to_statsig_api=True)
        updater = SpecUpdater(
            network=Mock(),
            data_adapter=options.data_store,
            options=options,
            diagnostics=Mock(),
            sdk_key="secret-key",
            error_boundary=Mock(),
            statsig_metadata={},
            shutdown_event=threading.Event(),
            context=Mock(),
        )

        self.assertEqual(
            updater._config_sync_strategies,
            [DataSource.DATASTORE, DataSource.NETWORK, DataSource.STATSIG_NETWORK],
        )

    def test_fallback_when_dcs_400(self, request_mock):
        self.stub_network(400)
        options = StatsigOptions(api=_network_stub.host, fallback_to_statsig_api=True,
                                 rulesets_sync_interval=1)
        init_details = statsig.initialize("secret-key", options)
        self.assertEqual(init_details.source, DataSource.STATSIG_NETWORK)
        self.assertTrue("raise for status error" in str(init_details.error))
        self.assertTrue(init_details.fallback_spec_used)
        self.get_gate_and_validate()
        self.wait_for_sync_and_validate()

    def test_fallback_when_dcs_500(self, request_mock):
        self.stub_network(500)
        options = StatsigOptions(api=_network_stub.host, fallback_to_statsig_api=True,
                                 rulesets_sync_interval=1)
        init_context = statsig.initialize("secret-key", options)
        self.assertEqual(init_context.source, DataSource.STATSIG_NETWORK)
        self.assertIsInstance(init_context.error, Exception)
        self.assertTrue(init_context.fallback_spec_used)
        self.get_gate_and_validate()
        self.wait_for_sync_and_validate()

    def test_fallback_when_dcs_invalid_json(self, request_mock):
        self.stub_network(202)
        options = StatsigOptions(api=_network_stub.host, fallback_to_statsig_api=True,
                                 rulesets_sync_interval=1)
        init_context = statsig.initialize("secret-key", options)
        self.assertEqual(init_context.source, DataSource.STATSIG_NETWORK)
        self.assertIsInstance(init_context.error, Exception)
        self.get_gate_and_validate()
        self.wait_for_sync_and_validate()

    def test_fallback_when_invalid_gzip_content(self, request_mock):
        self.stub_network(202, gzip=True)
        options = StatsigOptions(api=_network_stub.host, fallback_to_statsig_api=True,
                                 rulesets_sync_interval=1)
        statsig.initialize("secret-key", options)
        self.assertEqual(statsig.get_instance()._spec_store.init_source, DataSource.STATSIG_NETWORK)
        self.get_gate_and_validate()
        self.wait_for_sync_and_validate()

    def test_fallback_when_dcs_incomplete_read(self, request_mock):
        self.stub_network(200, incomplete_read=True)
        options = StatsigOptions(api=_network_stub.host, fallback_to_statsig_api=True,
                                 rulesets_sync_interval=1)
        init_context = statsig.initialize("secret-key", options)
        self.assertEqual(init_context.source, DataSource.STATSIG_NETWORK)
        self.assertIsInstance(init_context.error, Exception)
        self.get_gate_and_validate()
        self.wait_for_sync_and_validate()

    def test_fallback_when_dcs_incomplete_read_gzip(self, request_mock):
        self.stub_network(200, incomplete_read=True, gzip=True)
        options = StatsigOptions(api=_network_stub.host, fallback_to_statsig_api=True,
                                 rulesets_sync_interval=1)
        init_context = statsig.initialize("secret-key", options)
        self.assertEqual(init_context.source, DataSource.STATSIG_NETWORK)
        self.assertIsInstance(init_context.error, Exception)
        self.get_gate_and_validate()
        self.wait_for_sync_and_validate()

    def test_accept_encoding_header(self, mock_request):
        headers_verified = False

        def verify_headers(url, **kwargs):
            nonlocal headers_verified
            request_headers = kwargs.get('headers', {})
            self.assertEqual(request_headers.get('Accept-Encoding'), 'gzip, deflate, br')
            headers_verified = True
            return PARSED_CONFIG_SPEC

        _network_stub.stub_request_with_function(
            "download_config_specs/.*", 200, verify_headers)

        options = StatsigOptions(api=_network_stub.host)
        statsig.initialize("secret-key", options)
        statsig.shutdown()
        
        self.assertTrue(headers_verified, "Headers were not verified")

    def test_service_name_header_sent_without_forward_proxy_url(self, mock_request):
        headers_verified = False
        captured_service_name = None
        captured_user_agent = None

        def verify_headers(url, **kwargs):
            nonlocal headers_verified, captured_service_name, captured_user_agent
            request_headers = kwargs.get("headers", {})
            captured_service_name = request_headers.get("x-request-service")
            captured_user_agent = request_headers.get("User-Agent")
            headers_verified = True
            return PARSED_CONFIG_SPEC

        _network_stub.stub_request_with_function(
            "download_config_specs/.*", 200, verify_headers
        )

        options = StatsigOptions(api_for_download_config_specs=_network_stub.host)
        options.proxy_configs = {}
        options.service_name = "unit-test-service"
        statsig.initialize("secret-key", options)
        statsig.shutdown()

        self.assertTrue(headers_verified, "Service name header was not verified")
        self.assertEqual(captured_service_name, "unit-test-service")
        self.assertIn("statsig-sdk-type/py-server", captured_user_agent)
        self.assertIn("statsig-service/unit-test-service", captured_user_agent)

    def wait_for_sync_and_validate(self):
        _network_stub.stub_statsig_api_request_with_value("download_config_specs/.*", 200,
                                                          UPDATED_TIME_CONFIG_SPEC)
        for i in range(10):
            gate = statsig.get_feature_gate(self.test_user, "always_on_gate")
            if gate.get_evaluation_details().config_sync_time == 1631638014821:
                break
            time.sleep(0.1)
        
        gate = statsig.get_feature_gate(self.test_user, "always_on_gate")
        eval_detail: EvaluationDetails = gate.get_evaluation_details()
        self.assertEqual(eval_detail.config_sync_time, 1631638014821)

    def get_gate_and_validate(self):
        gate = statsig.get_feature_gate(self.test_user, "always_on_gate")
        eval_detail: EvaluationDetails = gate.get_evaluation_details()
        self.assertEqual(eval_detail.source, DataSource.STATSIG_NETWORK)
        self.assertEqual(eval_detail.config_sync_time, 1631638014811)
        self.assertTrue(self.__class__.dcs_called)
        self.assertTrue(self.__class__.statsig_dcs_called)
