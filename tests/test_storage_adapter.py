import json
import os
import unittest
from unittest.mock import patch

from statsig import statsig, IDataStore, StatsigOptions, StatsigUser
from network_stub import NetworkStub

with open(os.path.join(os.path.abspath(os.path.dirname(__file__)), '../testdata/download_config_specs.json')) as r:
    CONFIG_SPECS_RESPONSE = json.loads(r.read())


class _TestAdapter(IDataStore):
    is_shutdown = False
    data = {
        "statsig.cache": json.dumps({
            "dynamic_configs": [],
            "feature_gates": [{
                "name": "gate_from_adapter",
                "type": "feature_gate",
                "salt": "64fa52a6-4195-4658-b124-aa0be3ff8860",
                "enabled": True,
                "defaultValue": False,
                "rules": [{
                    "name": "6X3qJgyfwA81IJ2dxI7lYp",
                    "groupName": "public",
                    "passPercentage": 100,
                    "conditions": [{"type": "public"}],
                    "returnValue": True,
                    "id": "6X3qJgyfwA81IJ2dxI7lYp",
                    "salt": "6X3qJgyfwA81IJ2dxI7lYp",
                    "idType": "userID"
                }],
                "idType": "userID",
                "entity": "feature_gate"
            }],
            "id_lists": {},
            "layers": {},
            "layer_configs": [],
            "has_updates": True,
            "time": 1663803098618
        })
    }

    def get(self, key: str):
        return self.data.get(key, None)

    def set(self, key: str, value: str):
        self.data[key] = value

    def shutdown(self):
        self.is_shutdown = True


class TestStorageAdapter(unittest.TestCase):
    _api_override = "http://test-storage-adapter"
    _network_stub = NetworkStub(_api_override)
    _user = StatsigUser("a_user")
    _did_download_specs: bool
    _data_adapter: _TestAdapter
    _options: StatsigOptions

    def setUp(self) -> None:
        self._network_stub.reset()
        self._did_download_specs = False
        self._data_adapter = _TestAdapter()
        self._options = StatsigOptions(
            data_store=self._data_adapter, api=self._api_override, disable_diagnostics=True)

        def download_config_specs_callback(url: str, **kwargs):
            self._did_download_specs = True
            return CONFIG_SPECS_RESPONSE

        self._network_stub.stub_request_with_function(
            "download_config_specs/.*", 200, download_config_specs_callback)

    def tearDown(self) -> None:
        statsig.shutdown()

    @patch('requests.request', side_effect=_network_stub.mock)
    def test_loading(self, mock_request):
        statsig.initialize("secret-key", self._options)
        result = statsig.check_gate(self._user, "gate_from_adapter")
        self.assertTrue(result)

    @patch('requests.request', side_effect=_network_stub.mock)
    def test_saving(self, mock_request):
        self._data_adapter.data = {}
        statsig.initialize("secret-key", self._options)

        stored_string = self._data_adapter.data["statsig.cache"]
        expected_string = json.dumps(CONFIG_SPECS_RESPONSE)
        self.assertEqual(stored_string, expected_string)

    @patch('requests.request', side_effect=_network_stub.mock)
    def test_calls_network_when_adapter_is_empty(self, mock_request):
        self._data_adapter.data = {}
        statsig.initialize("secret-key", self._options)
        self.assertTrue(self._did_download_specs)

    @patch('requests.request', side_effect=_network_stub.mock)
    def test_no_network_call_when_adapter_has_value(self, mock_request):
        statsig.initialize("secret-key", self._options)
        self.assertFalse(self._did_download_specs)

    def test_bootstrap_is_ignored_when_data_store_is_set(self):
        options = StatsigOptions(
            data_store=self._data_adapter,
            api=self._api_override,
            disable_diagnostics=True,
            bootstrap_values=json.dumps({
                "time": 1,
                "feature_gates": [{
                    "name": "gate_from_bootstrap",
                    "type": "feature_gate",
                    "enabled": True,
                    "defaultValue": False,
                    "rules": [{
                        "name": "6N6Z8ODekNYZ7F8gFdoLP5",
                        "groupName": "everyone",
                        "passPercentage": 100,
                        "conditions": [{"type": "public", }],
                        "returnValue": True,
                        "id": "6N6Z8ODekNYZ7F8gFdoLP5",
                        "salt": "14862979-1468-4e49-9b2a-c8bb100eed8f"
                    }]
                }],
                "dynamic_configs": [],
                "layer_configs": [],
                "id_lists": {},
                "layers": {},
                "has_updates": True
            }))
        statsig.initialize("secret-key", options)

        result = statsig.check_gate(self._user, "gate_from_bootstrap")
        self.assertEqual(False, result)
