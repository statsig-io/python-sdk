import time
import unittest

from unittest.mock import patch
from statsig import StatsigServer, StatsigOptions, StatsigEnvironmentTier
from network_stub import NetworkStub


class TestBackgroundSync(unittest.TestCase):
    _client: StatsigServer
    _api_override = "http://test-background-sync"

    _network_stub = NetworkStub(_api_override)

    def setUp(self):
        self._network_stub.reset()

    def tearDown(self):
        self._client.shutdown()

    @patch('requests.request', side_effect=_network_stub.mock)
    def test_sync_cycle(self, mock_request):
        self.config_sync_count = 0
        self.idlist_sync_count = 0
        self.idlist_1_download_count = 0
        self.idlist_2_download_count = 0
        self.idlist_3_download_count = 0

        def download_config_specs_callback(url: str, **kwargs):
            self.config_sync_count = self.config_sync_count + 1
            return {
                "dynamic_configs": [{"name": "config_1"}],
                "feature_gates": [{"name": "gate_1"}, {"name": "gate_2"}],
                "id_lists": {
                    "list_1": True,
                    "list_2": True,
                },
                "has_updates": True,
                "time": 1,
            }

        self._network_stub.stub_request_with_function(
            "download_config_specs/.*", 200, download_config_specs_callback)

        def get_id_lists_callback(url: str, **kwargs):
            self.idlist_sync_count = self.idlist_sync_count + 1

            if self.idlist_sync_count == 1:
                return {
                    "list_1": {
                        "name": "list_1",
                        "size": 3,
                        "url": self._api_override + "/list_1",
                        "creationTime": 1,
                        "fileID": "file_id_1",
                    },
                    "list_2": {
                        "name": "list_2",
                        "size": 3,
                        "url": self._api_override + "/list_2",
                        "creationTime": 1,
                        "fileID": "file_id_2",
                    },
                }
            if self.idlist_sync_count == 2:
                return {
                    "list_1": {
                        "name": "list_1",
                        "size": 9,
                        "url": self._api_override + "/list_1",
                        "creationTime": 1,
                        "fileID": "file_id_1",
                    },
                }
            if self.idlist_sync_count == 3:
                return {
                    "list_1": {
                        "name": "list_1",
                        "size": 3,
                        "url": self._api_override + "/list_1",
                        "creationTime": 3,
                        "fileID": "file_id_1_a",
                    },
                }
            if self.idlist_sync_count == 4:
                return {
                    "list_1": {
                        "name": "list_1",
                        "size": 9,
                        "url": self._api_override + "/list_1",
                        "creationTime": 1,
                        "fileID": "file_id_1",
                    },
                }

            return {
                "list_1": {
                    "name": "list_1",
                    "size": 18,
                    "url": self._api_override + "/list_1",
                    "creationTime": 3,
                    "fileID": "file_id_1_a",
                },
                "list_3": {
                    "name": "list_3",
                    "size": 3,
                    "url": self._api_override + "/list_3",
                    "creationTime": 5,
                    "fileID": "file_id_3",
                },
            }

        self._network_stub.stub_request_with_function(
            "get_id_lists", 200, get_id_lists_callback)

        def id_list_1_callback(url: str, **kwargs):
            self.idlist_1_download_count = self.idlist_1_download_count + 1

            if self.idlist_sync_count == 1:
                return "+1\r"
            if self.idlist_sync_count == 2:
                return "+1\r-1\r+2\r"
            if self.idlist_sync_count == 3:
                # list_1 reset to new file
                return "+3\r"
            if self.idlist_sync_count == 4:
                # list_1 returned old file for some reason
                return "+1\r-1\r+2\r"
            if self.idlist_sync_count == 5:
                # corrupted response
                return "3"

            return "+3\r+4\r+5\r+4\r-4\r+6\r"

        self._network_stub.stub_request_with_function(
            "list_1", 200, id_list_1_callback)

        def id_list_2_callback(url: str, **kwargs):
            self.idlist_2_download_count = self.idlist_2_download_count + 1
            return "+a\r"

        self._network_stub.stub_request_with_function(
            "list_2", 200, id_list_2_callback)

        def id_list_3_callback(url: str, **kwargs):
            self.idlist_3_download_count = self.idlist_3_download_count + 1
            return "+0\r"

        self._network_stub.stub_request_with_function(
            "list_3", 200, id_list_3_callback)

        options = StatsigOptions(
            api=self._api_override,
            tier=StatsigEnvironmentTier.development,
            rulesets_sync_interval=1,
            idlists_sync_interval=1,
            disable_diagnostics=True
        )
        self._client = StatsigServer()
        self._client.initialize("secret-key", options)
        id_lists = self._client._spec_store.get_all_id_lists()

        self.assertEqual(self.config_sync_count, 1)
        self.assertEqual(self.idlist_sync_count, 1)
        self.assertEqual(self.idlist_1_download_count, 1)
        self.assertEqual(self.idlist_2_download_count, 1)
        self.assertEqual(self.idlist_3_download_count, 0)
        # initially should download 2 lists
        self.assertEqual(
            id_lists,
            dict(
                list_1=dict(
                    ids=set("1"),
                    readBytes=3,
                    url=self._api_override + "/list_1",
                    fileID="file_id_1",
                    creationTime=1,
                ),
                list_2=dict(
                    ids=set("a"),
                    readBytes=3,
                    url=self._api_override + "/list_2",
                    fileID="file_id_2",
                    creationTime=1,
                ),
            )
        )

        time.sleep(1.1)
        self.assertEqual(self.config_sync_count, 2)
        self.assertEqual(self.idlist_sync_count, 2)
        self.assertEqual(self.idlist_1_download_count, 2)
        self.assertEqual(self.idlist_2_download_count, 1)
        self.assertEqual(self.idlist_3_download_count, 0)

        # list_2 gets deleted; list_1 had an id deleted so now has a single id
        self.assertEqual(
            id_lists,
            dict(
                list_1=dict(
                    ids=set("2"),
                    readBytes=12,
                    url=self._api_override + "/list_1",
                    fileID="file_id_1",
                    creationTime=1,
                ),
            )
        )

        time.sleep(1.1)
        self.assertEqual(self.config_sync_count, 3)
        self.assertEqual(self.idlist_sync_count, 3)
        self.assertEqual(self.idlist_1_download_count, 3)
        self.assertEqual(self.idlist_2_download_count, 1)
        self.assertEqual(self.idlist_3_download_count, 0)
        # list_1 file changed
        self.assertEqual(
            id_lists,
            dict(
                list_1=dict(
                    ids=set("3"),
                    readBytes=3,
                    url=self._api_override + "/list_1",
                    fileID="file_id_1_a",
                    creationTime=3,
                ),
            )
        )

        time.sleep(1.1)
        self.assertEqual(self.config_sync_count, 4)
        self.assertEqual(self.idlist_sync_count, 4)
        self.assertEqual(self.idlist_1_download_count, 3)
        self.assertEqual(self.idlist_2_download_count, 1)
        self.assertEqual(self.idlist_3_download_count, 0)
        # endpoint returned old fileID for list_1, nothing should be
        # read/changed
        self.assertEqual(
            id_lists,
            dict(
                list_1=dict(
                    ids=set("3"),
                    readBytes=3,
                    url=self._api_override + "/list_1",
                    fileID="file_id_1_a",
                    creationTime=3,
                ),
            )
        )

        time.sleep(1.1)
        self.assertEqual(self.config_sync_count, 5)
        self.assertEqual(self.idlist_sync_count, 5)
        self.assertEqual(self.idlist_1_download_count, 4)
        self.assertEqual(self.idlist_2_download_count, 1)
        self.assertEqual(self.idlist_3_download_count, 1)
        # endpoint returned corrupted response for list_1; should keep previous
        # list_1 in memory, and list_3
        self.assertEqual(
            id_lists,
            dict(
                list_1=dict(
                    ids=set("3"),
                    readBytes=3,
                    url=self._api_override + "/list_1",
                    fileID="file_id_1_a",
                    creationTime=3,
                ),
                list_3=dict(
                    ids=set("0"),
                    readBytes=3,
                    url=self._api_override + "/list_3",
                    fileID="file_id_3",
                    creationTime=5,
                ),
            )
        )

        time.sleep(1.1)
        self.assertEqual(self.config_sync_count, 6)
        self.assertEqual(self.idlist_sync_count, 6)
        self.assertEqual(self.idlist_1_download_count, 5)
        self.assertEqual(self.idlist_2_download_count, 1)
        self.assertEqual(self.idlist_3_download_count, 1)

        # new ids for list_1, get appended; no change to list_3
        self.assertEqual(
            id_lists,
            dict(
                list_1=dict(
                    ids=set(["3", "5", "6"]),
                    readBytes=21,
                    url=self._api_override + "/list_1",
                    fileID="file_id_1_a",
                    creationTime=3,
                ),
                list_3=dict(
                    ids=set("0"),
                    readBytes=3,
                    url=self._api_override + "/list_3",
                    fileID="file_id_3",
                    creationTime=5,
                ),
            )
        )

        self._client.shutdown()

        # verify no more calls after shutdown() is called
        time.sleep(3)
        self.assertEqual(self.config_sync_count, 6)
        self.assertEqual(self.idlist_sync_count, 6)
        self.assertEqual(self.idlist_1_download_count, 5)
        self.assertEqual(self.idlist_2_download_count, 1)
        self.assertEqual(self.idlist_3_download_count, 1)

    @patch('requests.request', side_effect=_network_stub.mock)
    def test_sync_cycle_no_idlist(self, mock_request):
        self.config_sync_count = 0
        self.idlist_sync_count = 0

        def download_config_specs_callback(url: str, **kwargs):
            self.config_sync_count = self.config_sync_count + 1
            return {
                "dynamic_configs": [{"name": "config_1"}],
                "feature_gates": [{"name": "gate_1"}, {"name": "gate_2"}],
                "id_lists": {},
                "has_updates": True,
                "time": 1,
            }

        self._network_stub.stub_request_with_function(
            "download_config_specs/.*", 200, download_config_specs_callback)

        def get_id_lists_callback(url: str, **kwargs):
            self.idlist_sync_count = self.idlist_sync_count + 1

        self._network_stub.stub_request_with_function(
            "get_id_lists", 200, get_id_lists_callback)

        options = StatsigOptions(
            api=self._api_override,
            tier=StatsigEnvironmentTier.development,
            rulesets_sync_interval=1,
            idlists_sync_interval=1,
            disable_diagnostics=True
        )
        self._client = StatsigServer()
        self._client.initialize("secret-key", options)

        self.assertEqual(self.config_sync_count, 1)
        self.assertEqual(self.idlist_sync_count, 1)

        time.sleep(1.1)
        self.assertEqual(self.config_sync_count, 2)
        self.assertEqual(self.idlist_sync_count, 2)

        self._client.shutdown()
        time.sleep(3)
        self.assertEqual(self.config_sync_count, 2)
        self.assertEqual(self.idlist_sync_count, 2)

    @patch('requests.request', side_effect=_network_stub.mock)
    def test_dcs_retry(self, mock_request):
        self.config_sync_count = 0
        self.idlist_sync_count = 0

        def download_config_specs_response_callback(url: str, **kwargs):
            self.config_sync_count += 1
            if self.config_sync_count == 1:
                return "{}"
            return {
                "dynamic_configs": [{"name": "config_1"}],
                "feature_gates": [{"name": "gate_1"}, {"name": "gate_2"}],
                "id_lists": {},
                "has_updates": True,
                "time": 1,
            }

        def download_config_specs_code_callback(url: str, **kwargs):
            if self.config_sync_count == 1:
                return 500
            return 200

        self._network_stub.stub_request_with_function(
            "download_config_specs/.*",
            download_config_specs_code_callback,
            download_config_specs_response_callback
        )

        options = StatsigOptions(
            api=self._api_override,
            tier=StatsigEnvironmentTier.development,
            rulesets_sync_interval=2,
            idlists_sync_interval=2,
            disable_diagnostics=True
        )
        self._client = StatsigServer()
        self._client.initialize("secret-key", options)

        time.sleep(1)
        self.assertEqual(self.config_sync_count, 2)

        time.sleep(1)
        self.assertEqual(self.config_sync_count, 3)

        self._client.shutdown()
