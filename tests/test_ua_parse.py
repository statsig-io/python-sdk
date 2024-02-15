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


@patch('requests.request', side_effect=_network_stub.mock)
class TestStatsigE2E(unittest.TestCase):
    _logs = {}

    @classmethod
    @patch('requests.request', side_effect=_network_stub.mock)
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

    def test_ua_parser(self, mock_request):
        user_agents = {
             # initial motivation, windows XP.  Should not throw
            'Mozilla/5.0 (Windows NT 5.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.5414.87 ADG/11.0.4060 Safari/537.36': False,
            # Windows 7, firefox 78
            'Mozilla 5.0 (Windows NT 6.1; rv:78.0) Gecko/20100101 Firefox/78.0': True,
            # Windows 7, chrome 89
            'Mozilla/115.0 (Windows NT 6.1) AppleWebKit/1537.36 (KHTML, like Gecko) Chrome/89.0.1650.16 Safari/1537.36': True,
            # Windows 11, Edge 110
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36 Edg/110.0.1587.69': True
        }
        for ua, res in user_agents.items():
            user = StatsigUser(user_id="456", user_agent=ua)
            self.assertEqual(
                statsig.check_gate(user, "python_ua_debug"),
                res
            )

        statsig.shutdown()

if __name__ == '__main__':
    unittest.main()
