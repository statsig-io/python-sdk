import time
import os
import unittest
import json

from unittest.mock import patch
from network_stub import NetworkStub
from statsig import statsig, StatsigUser, StatsigOptions, StatsigEnvironmentTier

with open(os.path.join(os.path.abspath(os.path.dirname(__file__)), '../testdata/download_config_specs_unique_conditions.json')) as r:
    CONFIG_SPECS_RESPONSE = r.read()

_network_stub = NetworkStub("http://test-statsig-e2e")

# gate, user agent, expected evaluation
UA_GATE_CASES = [
    # initial motivation, windows XP.  Should not throw
    ("python_ua_debug", 'Mozilla/5.0 (Windows NT 5.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.5414.87 ADG/11.0.4060 Safari/537.36', False),
    # Windows 7, firefox 78
    ("python_ua_debug", 'Mozilla 5.0 (Windows NT 6.1; rv:78.0) Gecko/20100101 Firefox/78.0', True),
    # Windows 7, chrome 89
    ("python_ua_debug", 'Mozilla/115.0 (Windows NT 6.1) AppleWebKit/1537.36 (KHTML, like Gecko) Chrome/89.0.1650.16 Safari/1537.36', True),
    # Windows 11, Edge 110
    ("python_ua_debug", 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36 Edg/110.0.1587.69', True),
    # iPadOS carries the OS version the same way iOS does
    ("python_ios_ua_debug", 'Whatnot v26.26.0 (42), iPadOS 26.5, iPad13,19', True),
    ("python_ios_ua_debug", 'Whatnot v26.25.6 (1), iOS 26.5, iPhone16,1', True),
    # below the targeted version, so the version must still be read
    ("python_ios_ua_debug", 'Whatnot v17.4.0 (1), iPadOS 17.4, iPad13,19', False),
    # standard Safari iPad UA, no iPadOS token
    ("python_ios_ua_debug", 'Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1', False),
]


@patch('requests.Session.request', side_effect=_network_stub.mock)
class TestStatsigE2E(unittest.TestCase):
    _logs = {}

    @classmethod
    @patch('requests.Session.request', side_effect=_network_stub.mock)
    def setUpClass(cls, mock_request):
        _network_stub.stub_request_with_value(
            "download_config_specs/.*", 200, json.loads(CONFIG_SPECS_RESPONSE))
        _network_stub.stub_request_with_value("get_id_lists", 200, {})

        def log_event_callback(url: str, **kwargs):
            cls._logs = kwargs["json"]

        _network_stub.stub_request_with_function(
            "log_event", 202, log_event_callback)

        cls._logs = {}
        options = StatsigOptions(
            api=_network_stub.host,
            tier=StatsigEnvironmentTier.development,
            disable_diagnostics=True)

        statsig.initialize("secret-key", options)
        cls.initTime = round(time.time() * 1000)

    @classmethod
    def tearDownClass(cls):
        statsig.shutdown()

    def test_ua_parser(self, mock_request):
        for gate, ua, expected in UA_GATE_CASES:
            with self.subTest(gate=gate, user_agent=ua):
                user = StatsigUser(user_id="456", user_agent=ua)
                self.assertEqual(statsig.check_gate(user, gate), expected)

if __name__ == '__main__':
    unittest.main()
