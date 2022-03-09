import threading
import time
import unittest

from flask.json import jsonify
from .mockserver import MockServer

from statsig import statsig, StatsigServer, StatsigOptions, StatsigEnvironmentTier


class TestBackgroundSync(unittest.TestCase):
    def test_sync_cycle(self):
        server = MockServer(port=5677)
        server.start()

        self.config_sync_count = 0
        self.idlist_sync_count = 0
        self.idlist_1_download_count = 0
        self.idlist_2_download_count = 0
        self.idlist_3_download_count = 0

        config_response = {
            "dynamic_configs": [{"name": "config_1"}],
            "feature_gates": [{"name": "gate_1"}, {"name": "gate_2"}],
            "id_lists": {
                "list_1": True,
                "list_2": True,
            },
            "has_updates": True,
            "time": 1,
        }

        def config_callbackFunc():
            self.config_sync_count = self.config_sync_count + 1
            return jsonify(config_response)

        server.add_callback_response(
            "/download_config_specs",
            config_callbackFunc,
        )

        def idlist_callbackFunc():
            self.idlist_sync_count = self.idlist_sync_count + 1
            if self.idlist_sync_count == 1:
                return jsonify({
                    "list_1": {
                        "name": "list_1",
                        "size": 3,
                        "url": server.url + "/list_1",
                        "creationTime": 1,
                        "fileID": "file_id_1",
                    },
                    "list_2": {
                        "name": "list_2",
                        "size": 3,
                        "url": server.url + "/list_2",
                        "creationTime": 1,
                        "fileID": "file_id_2",
                    },
                })
            elif self.idlist_sync_count == 2:
                # list_1 increased, list_2 deleted
                return jsonify({
                    "list_1": {
                        "name": "list_1",
                        "size": 9,
                        "url": server.url + "/list_1",
                        "creationTime": 1,
                        "fileID": "file_id_1",
                    },
                })
            elif self.idlist_sync_count == 3:
                # list_1 reset to new file
                return jsonify({
                    "list_1": {
                        "name": "list_1",
                        "size": 3,
                        "url": server.url + "/list_1",
                        "creationTime": 3,
                        "fileID": "file_id_1_a",
                    },
                })
            elif self.idlist_sync_count == 4:
                # list_1 returned old file for some reason
                return jsonify({
                    "list_1": {
                        "name": "list_1",
                        "size": 9,
                        "url": server.url + "/list_1",
                        "creationTime": 1,
                        "fileID": "file_id_1",
                    },
                })
            # return same list and another one afterwards
            return jsonify({
                "list_1": {
                    "name": "list_1",
                    "size": 18,
                    "url": server.url + "/list_1",
                    "creationTime": 3,
                    "fileID": "file_id_1_a",
                },
                "list_3": {
                    "name": "list_3",
                    "size": 3,
                    "url": server.url + "/list_3",
                    "creationTime": 5,
                    "fileID": "file_id_3",
                },
            })

        server.add_callback_response(
            "/get_id_lists",
            idlist_callbackFunc,
        )

        def idlist_1_download_callbackFunc():
            self.idlist_1_download_count = self.idlist_1_download_count + 1
            if self.idlist_sync_count == 1:
                return "+1\r"
            elif self.idlist_sync_count == 2:
                return "+1\r-1\r+2\r"
            elif self.idlist_sync_count == 3:
                # list_1 reset to new file
                return "+3\r"
            elif self.idlist_sync_count == 4:
                # list_1 returned old file for some reason
                return "+1\r-1\r+2\r"
            elif self.idlist_sync_count == 5:
                # corrupted response
                return "3"
            return "+3\r+4\r+5\r+4\r-4\r+6\r"

        def idlist_2_download_callbackFunc():
            self.idlist_2_download_count = self.idlist_2_download_count + 1
            return "+a\r"

        def idlist_3_download_callbackFunc():
            self.idlist_3_download_count = self.idlist_3_download_count + 1
            return "+0\r"

        server.add_callback_response(
            "/list_1",
            idlist_1_download_callbackFunc,
            methods=('GET',)
        )
        server.add_callback_response(
            "/list_2",
            idlist_2_download_callbackFunc,
            methods=('GET',)
        )
        server.add_callback_response(
            "/list_3",
            idlist_3_download_callbackFunc,
            methods=('GET',)
        )

        options = StatsigOptions(
            api=server.url,
            tier=StatsigEnvironmentTier.development,
            rulesets_sync_interval=1,
            idlists_sync_interval=1,
        )
        client = StatsigServer()
        client.initialize("secret-key", options)
        id_lists = client._evaluator.get_id_lists()

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
                    url=server.url + "/list_1",
                    fileID="file_id_1",
                    creationTime=1,
                ),
                list_2=dict(
                    ids=set("a"),
                    readBytes=3,
                    url=server.url + "/list_2",
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
        # list_2 gets deleted; list_1 had an id deleted so now has 0 ids
        self.assertEqual(
            id_lists,
            dict(
                list_1=dict(
                    ids=set("2"),
                    readBytes=12,
                    url=server.url + "/list_1",
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
                    url=server.url + "/list_1",
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
        # endpoint returned old fileID for list_1, nothing should be read/changed
        self.assertEqual(
            id_lists,
            dict(
                list_1=dict(
                    ids=set("3"),
                    readBytes=3,
                    url=server.url + "/list_1",
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
        # endpoint returned corrupted response for list_1, should reset; list_3 get something
        self.assertEqual(
            id_lists,
            dict(
                list_3=dict(
                    ids=set("0"),
                    readBytes=3,
                    url=server.url + "/list_3",
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
                    readBytes=18,
                    url=server.url + "/list_1",
                    fileID="file_id_1_a",
                    creationTime=3,
                ),
                list_3=dict(
                    ids=set("0"),
                    readBytes=3,
                    url=server.url + "/list_3",
                    fileID="file_id_3",
                    creationTime=5,
                ),
            )
        )

        client.shutdown()

        # verify no more calls after shutdown() is called
        time.sleep(3)
        self.assertEqual(self.config_sync_count, 6)
        self.assertEqual(self.idlist_sync_count, 6)
        self.assertEqual(self.idlist_1_download_count, 5)
        self.assertEqual(self.idlist_2_download_count, 1)
        self.assertEqual(self.idlist_3_download_count, 1)
        server.shutdown_server()

    def test_sync_cycle_no_idlist(self):
        server = MockServer(port=5678)
        server.start()

        self.config_sync_count = 0
        self.idlist_sync_count = 0

        config_response = {
            "dynamic_configs": [{"name": "config_1"}],
            "feature_gates": [{"name": "gate_1"}, {"name": "gate_2"}],
            "id_lists": {},
            "has_updates": True,
            "time": 1,
        }

        def config_callbackFunc():
            self.config_sync_count = self.config_sync_count + 1
            return jsonify(config_response)

        server.add_callback_response(
            "/download_config_specs",
            config_callbackFunc,
        )

        def idlist_callbackFunc():
            self.idlist_sync_count = self.idlist_sync_count + 1
            return jsonify({})

        server.add_callback_response(
            "/get_id_lists",
            idlist_callbackFunc,
        )

        options = StatsigOptions(
            api=server.url,
            tier=StatsigEnvironmentTier.development,
            rulesets_sync_interval=1,
            idlists_sync_interval=1,
        )
        client = StatsigServer()
        client.initialize("secret-key", options)

        self.assertEqual(self.config_sync_count, 1)
        self.assertEqual(self.idlist_sync_count, 1)

        time.sleep(1.1)
        self.assertEqual(self.config_sync_count, 2)
        self.assertEqual(self.idlist_sync_count, 2)

        client.shutdown()
        time.sleep(3)
        self.assertEqual(self.config_sync_count, 2)
        self.assertEqual(self.idlist_sync_count, 2)

        server.shutdown_server()
