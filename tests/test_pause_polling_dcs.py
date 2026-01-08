import json
import os
import time
import unittest
from unittest.mock import patch

from network_stub import NetworkStub
from statsig import StatsigOptions, statsig

_network_stub = NetworkStub("http://test-pause-polling-dcs")

with open(os.path.join(os.path.abspath(os.path.dirname(__file__)), '../testdata/download_config_specs.json')) as r:
    CONFIG_SPECS_RESPONSE = r.read()
PARSED_CONFIG_SPEC = json.loads(CONFIG_SPECS_RESPONSE)


@patch('requests.Session.request', side_effect=_network_stub.mock)
class TestPausePollingDcs(unittest.TestCase):
    @classmethod
    @patch('requests.Session.request', side_effect=_network_stub.mock)
    def setUpClass(cls, mock_proxy):
        cls.dcs_called = False
        cls.dcs_call_count = 0

    def setUp(self):
        self.__class__.dcs_called = False
        self.__class__.dcs_call_count = 0

        def dcs_cb(url, **kwargs):
            self.__class__.dcs_called = True
            self.__class__.dcs_call_count += 1
            return PARSED_CONFIG_SPEC

        _network_stub.stub_request_with_value("get_id_lists", 200, {})
        _network_stub.stub_request_with_function("download_config_specs/.*", 200, dcs_cb)

    def tearDown(self):
        statsig.shutdown()
        _network_stub.reset()

    def test_pause_and_resume_dcs_polling(self, request_mock):
        options = StatsigOptions(api=_network_stub.host, rulesets_sync_interval=1)
        statsig.initialize("secret-key", options)

        paused_wait_s = 3.0
        resume_timeout_s = 5.0

        def wait_for_new_dcs_calls(prev_count: int, timeout_s: float) -> bool:
            deadline = time.time() + timeout_s
            while time.time() < deadline:
                if self.__class__.dcs_call_count > prev_count:
                    return True
                time.sleep(0.05)
            return False

        # ignore the initialize-time DCS fetch
        self.__class__.dcs_called = False
        self.__class__.dcs_call_count = 0

        # OFF -> ON -> OFF -> ON
        statsig.pause_polling_dcs()
        prev = self.__class__.dcs_call_count
        time.sleep(paused_wait_s)
        self.assertEqual(prev, self.__class__.dcs_call_count)

        statsig.start_polling_dcs()
        prev = self.__class__.dcs_call_count
        self.assertTrue(wait_for_new_dcs_calls(prev, timeout_s=resume_timeout_s))

        statsig.pause_polling_dcs()
        prev = self.__class__.dcs_call_count
        time.sleep(paused_wait_s)
        self.assertEqual(prev, self.__class__.dcs_call_count)

        statsig.start_polling_dcs()
        prev = self.__class__.dcs_call_count
        self.assertTrue(wait_for_new_dcs_calls(prev, timeout_s=resume_timeout_s))
