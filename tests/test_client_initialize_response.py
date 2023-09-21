import os
import unittest
import time

import requests

from statsig import StatsigOptions, statsig, StatsigUser, StatsigServer
from statsig.evaluator import _ConfigEvaluation
from unittest.mock import MagicMock

user = {
    'userID': '123',
    'email': 'test@statsig.com',
    'country': 'US',
    'custom': {
        'test': '123',
    },
    'customIDs': {
        'stableID': '12345',
    }
}

user_for_sdk = StatsigUser(user_id=user["userID"], email=user["email"], country=user["country"],
                           custom=user["custom"], custom_ids=user["customIDs"])


@unittest.skip("Disabled until optimizations are complete")
class TestClientInitializeResponse(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        try:
            cls.client_key = os.environ["test_client_key"]
            cls.secret_key = os.environ["test_api_key"]
        except Exception as e:
            print("THIS TEST IS EXPECTED TO FAIL FOR NON-STATSIG EMPLOYEES! If this is the only test failing, "
                  "please proceed to submit a pull request. If you are a Statsig employee, chat with jkw.")
            raise Exception("Failed to read sdk keys") from e

    def tearDown(self) -> None:
        statsig.shutdown()

    def test_prod(self):
        server_res, sdk_res = self.get_initialize_responses(
            'https://statsigapi.net/v1')
        self.validate_consistency(server_res, sdk_res)

    def test_prod_with_dev(self):
        server_res, sdk_res = self.get_initialize_responses(
            'https://statsigapi.net/v1', 'development')
        self.validate_consistency(server_res, sdk_res)

    def test_none_result(self):
        statsig.initialize('secret-no-valid-key',
                           StatsigOptions(local_mode=True, disable_diagnostics=True))
        result = statsig.get_client_initialize_response(user_for_sdk)
        self.assertIsNone(result)

    def test_unsupported_server(self):
        server_res, sdk_res = self.get_initialize_responses(
            'https://statsigapi.net/v1', None, True)
        for key in server_res:
            if isinstance(server_res[key], dict):
                for subkey in server_res[key]:
                    sdk_value = sdk_res[key][subkey]

                    if key == "feature_gates":
                        self.assertEqual(False, sdk_value["value"])
                    elif key == "dynamic_configs" or key == "layer_configs":
                        if not sdk_value.get("is_in_layer", False):
                            self.assertEqual({}, sdk_value["value"])

    def get_initialize_responses(
            self, api: str, environment=None, force_unsupported=False):
        server_user = user.copy()
        options = StatsigOptions(api=api, disable_diagnostics=True)

        if environment is not None:
            server_user["statsigEnvironment"] = {'tier': environment}
            options.set_environment_parameter("tier", environment)

        response = requests.post(
            url=api + '/initialize',
            json={'user': server_user,
                  'statsigMetadata': {'sdkType': 'consistency-test', 'sessionID': 'x123'}},
            headers={
                'Content-type': 'application/json',
                'STATSIG-API-KEY': self.client_key,
                'STATSIG-CLIENT-TIME': str(round(time.time() * 1000)),
            })
        server_res = response.json()

        statsig.initialize(self.secret_key, options)

        if force_unsupported:
            statsig.get_instance()._evaluator._Evaluator__eval_config = MagicMock(
                return_value=_ConfigEvaluation(True))

        sdk_res = statsig.get_client_initialize_response(user_for_sdk)

        return server_res, sdk_res

    def validate_consistency(self, server_data, sdk_data):
        def rm_secondary_exposure_hashes(value):
            if not isinstance(value, dict):
                return value

            se = value.get("secondary_exposures", [])
            use = value.get("undelegated_secondary_exposures", [])
            if se is None and use is None:
                return value

            def overwrite_name(exposure):
                exposure["gate"] = "__REMOVED_FOR_TEST__"
                return exposure

            value["secondary_exposures"] = list(map(overwrite_name, se))
            value["undelegated_secondary_exposures"] = list(
                map(overwrite_name, use))
            return value

        for key in server_data:
            if isinstance(server_data[key], dict):
                for sub_key in server_data[key]:
                    server_val = rm_secondary_exposure_hashes(
                        server_data[key][sub_key])
                    sdk_val = rm_secondary_exposure_hashes(
                        sdk_data[key][sub_key])
                    self.assertEqual(server_val, sdk_val)
            elif key not in ["generator", "time"]:
                self.assertEqual(sdk_data[key], server_data[key])


if __name__ == '__main__':
    unittest.main()
