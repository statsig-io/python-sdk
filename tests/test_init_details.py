import json
import os
import unittest
from unittest.mock import patch

from statsig import StatsigOptions, statsig, IDataStore
from statsig.statsig_options import DataSource
from tests.network_stub import NetworkStub

with open(os.path.join(os.path.abspath(os.path.dirname(__file__)), '../testdata/download_config_specs.json')) as r:
    CONFIG_SPECS_RESPONSE = r.read()
PARSED_CONFIG_SPEC = json.loads(CONFIG_SPECS_RESPONSE)

_network_stub = NetworkStub("http://test-init-details")


@patch('requests.Session.request', side_effect=_network_stub.mock)
class TestInitDetails(unittest.TestCase):

    @classmethod
    def setUp(cls):
        _network_stub.reset()

    def test_init_network_success(self, mock_request):
        _network_stub.stub_request_with_value(
            "download_config_specs/.*", 200, PARSED_CONFIG_SPEC)
        options = StatsigOptions(api=_network_stub.host)
        init_details = statsig.initialize("secret-key", options)
        statsig.shutdown()
        self.assertEqual(init_details.init_success, True)
        self.assertEqual(init_details.store_populated, True)
        self.assertEqual(init_details.source, DataSource.NETWORK)

    def test_init_network_failure(self, mock_request):
        _network_stub.stub_request_with_value(
            "download_config_specs/.*", 500, "{}")
        options = StatsigOptions(api=_network_stub.host)
        init_details = statsig.initialize("secret-key", options)
        statsig.shutdown()
        self.assertEqual(init_details.init_success, True)
        self.assertEqual(init_details.store_populated, False)
        self.assertEqual(init_details.source, DataSource.UNINITIALIZED)

    def test_init_bootstrap_success(self, mock_request):
        options = StatsigOptions(api=_network_stub.host, bootstrap_values=CONFIG_SPECS_RESPONSE)
        init_details = statsig.initialize("secret-key", options)
        statsig.shutdown()
        self.assertEqual(init_details.init_success, True)
        self.assertEqual(init_details.store_populated, True)
        self.assertEqual(init_details.source, DataSource.BOOTSTRAP)

    def test_init_bootstrap_failed(self, mock_request):
        _network_stub.stub_request_with_value(
            "download_config_specs/.*", 200, PARSED_CONFIG_SPEC)
        options = StatsigOptions(api=_network_stub.host, bootstrap_values="{}")
        init_details = statsig.initialize("secret-key", options)
        statsig.shutdown()
        self.assertEqual(init_details.init_success, True)
        self.assertEqual(init_details.store_populated, True)
        self.assertEqual(init_details.source, DataSource.NETWORK)

    def test_init_dataadapter_success(self, mock_request):
        class _TestAdapter(IDataStore):
            def get(self, key: str):
                return CONFIG_SPECS_RESPONSE

        options = StatsigOptions(api=_network_stub.host, data_store=_TestAdapter())
        init_details = statsig.initialize("secret-key", options)
        statsig.shutdown()
        self.assertEqual(init_details.init_success, True)
        self.assertEqual(init_details.store_populated, True)
        self.assertEqual(init_details.source, DataSource.DATASTORE)

    def test_init_dataadapter_failed(self, mock_request):
        class _TestAdapter(IDataStore):
            def get(self, key: str):
                return {}

        _network_stub.stub_request_with_value(
            "download_config_specs/.*", 200, PARSED_CONFIG_SPEC)
        options = StatsigOptions(api=_network_stub.host, data_store=_TestAdapter())
        init_details = statsig.initialize("secret-key", options)
        statsig.shutdown()
        self.assertEqual(init_details.init_success, True)
        self.assertEqual(init_details.store_populated, True)
        self.assertEqual(init_details.source, DataSource.NETWORK)
