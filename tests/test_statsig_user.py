import json
import unittest
from uuid import uuid4
from user_agents import parse
import semver

from statsig import StatsigUser
from statsig.statsig_environment_tier import StatsigEnvironmentTier


class TestStatsigUser(unittest.TestCase):

    def test_uuid(self):
        id = uuid4()
        user = StatsigUser(id)
        user_string = json.dumps(user.to_dict())
        self.assertEqual(json.loads(user_string)["userID"], str(id))

    def test_numeric(self):
        user = StatsigUser("test")
        user.ip = 111
        user_string = json.dumps(user.to_dict())
        self.assertEqual(json.loads(user_string)["ip"], "111")

    def test_environment(self):
        user = StatsigUser("test")
        user._statsig_environment = {
            "tier": StatsigEnvironmentTier.development}
        user_string = json.dumps(user.to_dict())
        self.assertEqual(json.loads(user_string)[
                             "statsigEnvironment"]["tier"], "development")

    def test_environment_string(self):
        user = StatsigUser("test")
        user._statsig_environment = {"tier": "staging"}
        user_string = json.dumps(user.to_dict())
        self.assertEqual(json.loads(user_string)[
                             "statsigEnvironment"]["tier"], "staging")

    def test_serialize_for_evaluation(self):
        user = StatsigUser(user_id="hi", private_attributes={"abc": 123})
        user_string = json.dumps(user.to_dict(True))
        self.assertEqual(json.loads(user_string)[
                             "privateAttributes"]["abc"], 123)

    def test_stringify_user_id(self):
        user = StatsigUser(123)
        self.assertEqual(user.user_id, '123')

    def test_all(self):
        id = uuid4()
        ua_string = 'Mozilla/5.0 (iPhone; CPU iPhone OS 5_1 like Mac OS X) AppleWebKit/534.46 (KHTML, like Gecko) Version/5.1 Mobile/9B179 Safari/7534.48.3'
        user_agent = parse(ua_string)
        ver = semver.VersionInfo.parse('1.22.3')
        user = StatsigUser(
            user_id=id,
            email="jkw+123@statsig.com",
            user_agent=user_agent,
            custom_ids={"custom": 123},
            private_attributes={"app_version": ver},
            country="MX",
            locale="en_US",
            app_version=ver,
            custom={"GB": "league?"}
        )
        user._statsig_environment = {"tier": "production"}
        user_string = json.dumps(user.to_dict())
        self.assertEqual(json.loads(user_string)["userID"], str(id))
        self.assertEqual(json.loads(user_string)["userAgent"], str(user_agent))
        self.assertEqual(json.loads(user_string)["appVersion"], "1.22.3")
        self.assertEqual(json.loads(user_string)[
                             "email"], "jkw+123@statsig.com")
        self.assertEqual(json.loads(user_string)["customIDs"]["custom"], '123')
        self.assertEqual(json.loads(user_string)["country"], "MX")
        self.assertEqual(json.loads(user_string)["locale"], "en_US")
        self.assertEqual(json.loads(user_string)["custom"]["GB"], "league?")
        self.assertEqual(
            "private_attributes" in json.loads(user_string), False)
