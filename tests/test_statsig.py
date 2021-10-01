import unittest
import time

from statsig.statsig_user import StatsigUser
from statsig.statsig_options import StatsigOptions
from statsig.statsig_event import StatsigEvent
from statsig import statsig

SECRET_KEY = ""

class TestStatsig(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        statsig.initialize(SECRET_KEY)

    def test_logs(self):
        user = StatsigUser("test")
        evt = StatsigEvent(user, "test_native_python")
        statsig.log_event(evt)
        self.assertEqual(True, True)

    def test_check_gate(self):
        user = StatsigUser("test")
        self.assertEqual(False, statsig.check_gate(user, "doesnt_matter"))
    
    def test_on_gate(self):
        user = StatsigUser("4")
        self.assertEqual(False, statsig.check_gate(user, "test123"))
        user = StatsigUser("2")
        self.assertEqual(True, statsig.check_gate(user, "test123"))
    
    def test_dynamic_config(self):
        user = StatsigUser("test")
        self.assertEqual({}, statsig.get_config(user, "doesnt_matter").get_value())

    def tearDown(self):
        statsig.shutdown()
