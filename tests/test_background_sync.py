import time
import unittest

from flask.json import jsonify
from .mockserver import MockServer

from statsig import statsig, statsig_server
from statsig.statsig_options import StatsigOptions
from statsig.statsig_environment_tier import StatsigEnvironmentTier


class TestStatsigE2E(unittest.TestCase):

    def test_sync_cycle(self):
        server = MockServer(port=5677)
        server.start()

        self.config_sync_count = 0
        self.idlist_sync_count = 0

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
            self.config_sync_count = self.config_sync_count+1
            return jsonify(config_response)

        server.add_callback_response(
            "/download_config_specs", config_callbackFunc,)

        def idlist_callbackFunc():
            self.idlist_sync_count = self.idlist_sync_count+1
            return jsonify({"add_ids": ["1", "2"], "remove_ids": [], "time": 1})

        server.add_callback_response(
            "/download_id_list", idlist_callbackFunc,)

        options = StatsigOptions(
            api=server.url, tier=StatsigEnvironmentTier.development, rulesets_sync_interval=1, idlists_sync_interval=1)
        statsig.initialize("secret-key", options)

        self.assertEqual(self.config_sync_count, 1)
        self.assertEqual(self.idlist_sync_count, 2)

        time.sleep(1.1)
        self.assertEqual(self.config_sync_count, 2)
        self.assertEqual(self.idlist_sync_count, 4)

        time.sleep(1.1)
        self.assertEqual(self.config_sync_count, 3)
        self.assertEqual(self.idlist_sync_count, 6)

        statsig.shutdown()
        time.sleep(3)
        self.assertEqual(self.config_sync_count, 3)
        self.assertEqual(self.idlist_sync_count, 6)

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
            self.config_sync_count = self.config_sync_count+1
            return jsonify(config_response)

        server.add_callback_response(
            "/download_config_specs", config_callbackFunc,)

        def idlist_callbackFunc():
            self.idlist_sync_count = self.idlist_sync_count+1
            return jsonify({"add_ids": ["1", "2"], "remove_ids": [], "time": 1})

        server.add_callback_response(
            "/download_id_list", idlist_callbackFunc,)

        options = StatsigOptions(
            api=server.url, tier=StatsigEnvironmentTier.development, rulesets_sync_interval=1, idlists_sync_interval=1)
        client = statsig_server.StatsigServer()
        client.initialize("secret-key", options)

        self.assertEqual(self.config_sync_count, 1)
        self.assertEqual(self.idlist_sync_count, 0)

        time.sleep(1.1)
        self.assertEqual(self.config_sync_count, 2)
        self.assertEqual(self.idlist_sync_count, 0)

        client.shutdown()
        time.sleep(3)
        self.assertEqual(self.config_sync_count, 2)
        self.assertEqual(self.idlist_sync_count, 0)

        server.shutdown_server()
