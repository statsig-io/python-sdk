import unittest

from subprocess import call
clean = [
    'make',
    '-C',
    'statsig/shared/',
    'clean',
]

make = [
    'make',
    '-C',
    'statsig/shared/',
    'install',
]

call(clean)
call(make)

import requests
from statsig.statsig_user import StatsigUser
from statsig.statsig_options import StatsigOptions
from statsig import statsig

import io
import sys
import time
try:
    f = io.open("../../ops/secrets/prod_keys/statsig-rulesets-eval-consistency-test-secret.key", mode="r", encoding="utf-8")

except OSError:
    print("THIS TEST IS EXPECTED TO FAIL FOR NON-STATSIG EMPLOYEES! If this is the only test failing, please proceed to submit a pull request. If you are a Statsig employee, chat with jkw.")
    sys.exit()

SDK_KEY = f.read()
f.close()

TEST_URLS = [
    "https://api.statsig.com/v1",
]

class ServerSDKConsistencyTest(unittest.TestCase):
    def setUp(self):
        api = "https://api.statsig.com/v1"
        headers = {
            'STATSIG-API-KEY': SDK_KEY,
            'STATSIG-CLIENT-TIME': str(round(time.time() * 1000)),
        }
        response = requests.post(api + "/rulesets_e2e_test", headers=headers)
        self.data = response.json()
        options = StatsigOptions()
        options.api = api
        statsig.initialize(SDK_KEY, options)

    def test_consistency(self):
        for entry in self.data:
            for val in self.data[entry]:
                user = val["user"]
                statsig_user = StatsigUser(user["userID"])
                statsig_user.app_version = user["appVersion"]
                statsig_user.user_agent = user["userAgent"]
                statsig_user.ip = user["ip"]
                if "email" in user:
                    statsig_user.email = user["email"]
                if "statsigEnvironment" in user:
                    statsig_user.statsig_environment = user["statsigEnvironment"]
                if "custom" in user:
                    statsig_user.custom = user["custom"]
                if "privateAttributes" in user:
                    statsig_user.private_attributes = user["privateAttributes"]
                gates = val["feature_gates_v2"]
                for name in gates:
                    sdk_result = statsig.check_gate(statsig_user, name)
                    server_result = gates[name]
                    self.assertEqual(sdk_result, server_result["value"])

if __name__ == '__main__':
    unittest.main()