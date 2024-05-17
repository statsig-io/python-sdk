import os
from statsig import StatsigUser, StatsigServer, StatsigOptions
import unittest
import time
import requests

from statsig.utils import HashingAlgorithm

TEST_URLS = [
    "https://statsigapi.net/v1",
    "https://staging.statsigapi.net/v1"
]


def _construct_statsig_user(user_values) -> StatsigUser:
    statsig_user = StatsigUser(
        user_id=user_values.get("userID"),
        custom_ids=user_values.get("customIDs"))
    statsig_user.app_version = user_values.get("appVersion")
    statsig_user.user_agent = user_values.get("userAgent")
    statsig_user.ip = user_values.get("ip")
    statsig_user.locale = user_values.get("locale")
    statsig_user.email = user_values.get("email")
    statsig_user._statsig_environment = user_values.get(
        "statsigEnvironment")
    statsig_user.custom = user_values.get("custom")
    statsig_user.private_attributes = user_values.get(
        "privateAttributes")

    return statsig_user


class ServerSDKConsistencyTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        try:
            cls.SDK_KEY = os.environ["test_api_key"]
        except Exception as e:
            print(
                "THIS TEST IS EXPECTED TO FAIL FOR NON-STATSIG EMPLOYEES! If this is the only test failing, please proceed to submit a pull request. If you are a Statsig employee, chat with jkw.")
            raise Exception("Failed to read sdk key") from e

    def test_all_regions(self):
        for api in TEST_URLS:
            headers = {
                'STATSIG-API-KEY': self.SDK_KEY,
                'STATSIG-CLIENT-TIME': str(round(time.time() * 1000)),
            }
            response = requests.post(
                api + "/rulesets_e2e_test", headers=headers)
            self.data = response.json()
            options = StatsigOptions(api=api, disable_diagnostics=True)
            self.sdk = StatsigServer()
            print(api)
            self.sdk.initialize(self.SDK_KEY, options)
            self._test_consistency()
            self.sdk.shutdown()

    def _test_consistency(self):
        for entry in self.data:
            for val in self.data[entry]:
                statsig_user = _construct_statsig_user(val["user"])
                sdk_results = self.sdk._evaluator.get_client_initialize_response(
                    statsig_user, HashingAlgorithm.NONE)

                self._test_gate_results(
                    statsig_user, val["feature_gates_v2"],
                    sdk_results["feature_gates"])
                self._test_config_results(
                    statsig_user, val["dynamic_configs"],
                    sdk_results["dynamic_configs"])
                self._test_layer_results(
                    statsig_user, val["layer_configs"],
                    sdk_results["layer_configs"])

        print("[end]")

    def _test_gate_results(self, statsig_user: StatsigUser, server, local):
        for name in server:
            sdk_result = local[name]
            server_result = server[name]
            if sdk_result["value"] != server_result["value"]:
                print(
                    f'\nDifferent values for gate {name} user: {statsig_user.to_dict(True)}')
                print(
                    f'\nExpected: {server_result["value"]}, Actual: {sdk_result["value"]}')

            if sdk_result["rule_id"] != server_result["rule_id"]:
                print(
                    f'\nDifferent rule_id for gate {name} user: {statsig_user.to_dict(True)}')
                print(
                    f'\nExpected: {server_result["rule_id"]}, Actual: {sdk_result["rule_id"]}')

            if sdk_result["secondary_exposures"] != server_result["secondary_exposures"]:
                print(
                    f'\nDifferent secondary_exposures for gate {name} user: {statsig_user.to_dict(True)}')
                print(
                    f'\nExpected: {server_result["secondary_exposures"]}, Actual: {sdk_result["secondary_exposures"]}')

    def _test_config_results(self, statsig_user: StatsigUser, server, local):
        for name in server:
            sdk_result = local[name]
            server_result = server[name]
            if sdk_result["value"] != server_result["value"]:
                print(
                    f'\nDifferent values for config {name} user: {statsig_user.to_dict(True)}')
                print(
                    f'\nExpected: {server_result["value"]}, Actual: {sdk_result["value"]}')

            if sdk_result["rule_id"] != server_result["rule_id"]:
                print(
                    f'\nDifferent rule_id for config {name} user: {statsig_user.to_dict(True)}')
                print(
                    f'\nExpected: {server_result["rule_id"]}, Actual: {sdk_result["rule_id"]}')

            if sdk_result["secondary_exposures"] != server_result["secondary_exposures"]:
                print(
                    f'\nDifferent secondary_exposures for config {name} user: {statsig_user.to_dict(True)}')
                print(
                    f'\nExpected: {server_result["secondary_exposures"]}, Actual: {sdk_result["secondary_exposures"]}')

    def _test_layer_results(self, statsig_user: StatsigUser, server, local):
        for name in server:
            sdk_result = local[name]
            server_result = server[name]
            if sdk_result["value"] != server_result["value"]:
                print(
                    f'\nDifferent values for layer {name} user: {statsig_user.to_dict(True)}')
                print(
                    f'\nExpected: {server_result["value"]}, Actual: {sdk_result["value"]}')

            if sdk_result["rule_id"] != server_result["rule_id"]:
                print(
                    f'\nDifferent rule_id for layer {name} user: {statsig_user.to_dict(True)}')
                print(
                    f'\nExpected: {server_result["rule_id"]}, Actual: {sdk_result["rule_id"]}')

            if sdk_result["secondary_exposures"] != server_result["secondary_exposures"]:
                print(
                    f'\nDifferent secondary_exposures for layer {name} user: {statsig_user.to_dict(True)}')
                print(
                    f'\nExpected: {server_result["secondary_exposures"]}, Actual: {sdk_result["secondary_exposures"]}')

            if sdk_result["undelegated_secondary_exposures"] != server_result[
                    "undelegated_secondary_exposures"]:
                print(
                    f'\nDifferent undelegated_secondary_exposures for layer {name} user: {statsig_user.to_dict(True)}')
                print(
                    f'\nExpected: {server_result["undelegated_secondary_exposures"]}, Actual: {sdk_result["undelegated_secondary_exposures"]}')


if __name__ == '__main__':
    unittest.main()
