import unittest
import requests
from statsig.statsig_environment_tier import StatsigEnvironmentTier
from statsig.statsig_user import StatsigUser
from statsig.statsig_options import StatsigOptions
from statsig.statsig_server import StatsigServer

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
    "https://latest.api.statsig.com/v1",
]

class ServerSDKConsistencyTest(unittest.TestCase):
    
    def test_all_regions(self):
        for api in TEST_URLS:
            headers = {
                'STATSIG-API-KEY': SDK_KEY,
                'STATSIG-CLIENT-TIME': str(round(time.time() * 1000)),
            }
            response = requests.post(api + "/rulesets_e2e_test", headers=headers)
            self.data = response.json()
            options = StatsigOptions(api=api)
            self.sdk = StatsigServer()
            print(api)
            self.sdk.initialize(SDK_KEY, options)
            self._test_consistency()
            self.sdk.shutdown()

    def _test_consistency(self):
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
                    statsig_user._statsig_environment = user["statsigEnvironment"]
                if "custom" in user:
                    statsig_user.custom = user["custom"]
                if "privateAttributes" in user:
                    statsig_user.private_attributes = user["privateAttributes"]
                gates = val["feature_gates_v2"]
                for name in gates:
                    eval_result = self.sdk._evaluator.check_gate(statsig_user, name)
                    sdk_result = self.sdk.check_gate(statsig_user, name)
                    server_result = gates[name]
                    if eval_result.boolean_value != server_result["value"]:
                        print(f'\nDifferent values for gate {name} user: {statsig_user.to_dict(True)}')
                        print(f'\nExpected: {server_result["value"]}, Actual: {eval_result.boolean_value}')
                    self.assertEqual(eval_result.boolean_value, server_result["value"])
                    self.assertEqual(eval_result.boolean_value, sdk_result)

                    if eval_result.rule_id != server_result["rule_id"]:
                        print(f'\nDifferent rule_id for gate {name} user: {statsig_user.to_dict(True)}')
                        print(f'\nExpected: {server_result["rule_id"]}, Actual: {eval_result.rule_id}')
                    self.assertEqual(eval_result.rule_id, server_result["rule_id"])

                    if eval_result.secondary_exposures != server_result["secondary_exposures"]:
                        print(f'\nDifferent secondary_exposures for gate {name} user: {statsig_user.to_dict(True)}')
                        print(f'\nExpected: {server_result["secondary_exposures"]}, Actual: {eval_result.secondary_exposures}')
                    self.assertEqual(eval_result.secondary_exposures, server_result.get("secondary_exposures"))
                    print(".", end="")

                configs = val["dynamic_configs"]
                for name in configs:
                    eval_result = self.sdk._evaluator.get_config(statsig_user, name)
                    sdk_result = self.sdk.get_config(statsig_user, name)
                    server_result = configs[name]
                    if eval_result.json_value != server_result["value"]:
                        print(f'\nDifferent values for config {name} user: {statsig_user.to_dict(True)}')
                        print(f'\nExpected: {server_result["value"]}, Actual: {eval_result.json_value}')
                    self.assertEqual(eval_result.json_value, server_result["value"])
                    self.assertEqual(eval_result.json_value, sdk_result.get_value())

                    if eval_result.rule_id != server_result["rule_id"]:
                        print(f'\nDifferent rule_id for config {name} user: {statsig_user.to_dict(True)}')
                        print(f'\nExpected: {server_result["rule_id"]}, Actual: {eval_result.rule_id}')
                    self.assertEqual(eval_result.rule_id, server_result["rule_id"])

                    if eval_result.secondary_exposures != server_result["secondary_exposures"]:
                        print(f'\nDifferent secondary_exposures for config {name} user: {statsig_user.to_dict(True)}')
                        print(f'\nExpected: {server_result["secondary_exposures"]}, Actual: {eval_result.secondary_exposures}')
                    self.assertEqual(eval_result.secondary_exposures, server_result.get("secondary_exposures"))
                    print(".", end="")
        print("[end]")


if __name__ == '__main__':
    unittest.main()