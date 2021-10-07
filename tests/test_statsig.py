import time
import unittest
from statsig.statsig_environment_tier import StatsigEnvironmentTier

from statsig.statsig_user import StatsigUser
from statsig.statsig_options import StatsigOptions
from statsig.statsig_event import StatsigEvent
from statsig import statsig

SECRET_KEY = ""

class TestStatsig(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        options = StatsigOptions(tier=StatsigEnvironmentTier.production)
        statsig.initialize(SECRET_KEY, options)

    def test_logs(self):
        user = StatsigUser("test")
        evt = StatsigEvent(user, "test_native_python")
        statsig.log_event(evt)
        self.assertEqual(True, True)
    
    def test_polling(self):
        for i in range(1, 25):
            user = StatsigUser("test")
            print(statsig.check_gate(user, "polling"))
            time.sleep(3)

    def test_check_gate(self):
        user = StatsigUser("test")
        self.assertEqual(False, statsig.check_gate(user, "environments"))
    
    def test_on_gate(self):
        user = StatsigUser("4")
        self.assertEqual(False, statsig.check_gate(user, "test123"))
        user = StatsigUser("2")
        self.assertEqual(True, statsig.check_gate(user, "test123"))
    
    def test_dynamic_config(self):
        user = StatsigUser("test")
        self.assertEqual({}, statsig.get_config(user, "doesnt_matter").get_value())

    @classmethod
    def tearDownClass(cls):
        statsig.shutdown()

if __name__ == '__main__':
    unittest.main()