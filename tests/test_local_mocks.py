from threading import local
import unittest

from statsig import StatsigServer, StatsigUser, StatsigOptions


class TestLocalMocks(unittest.TestCase):

    def test_local_mode_defaults(self):
        options = StatsigOptions(local_mode=True)
        server = StatsigServer()
        server.initialize("secret-key", options)

        user = StatsigUser("123", email="testuser@statsig.com")

        self.assertEqual(
            server.check_gate(user, "any_gate"),
            False
        )

        self.assertEqual(
            server.get_config(user, "any_config").get_value(),
            {}
        )

        self.assertEqual(
            server.get_experiment(user, "any_experiment").get_value(),
            {}
        )

    def test_override_gate(self):
        options = StatsigOptions(local_mode=True)
        server = StatsigServer()
        server.initialize("secret-key", options)

        user_one = StatsigUser("123", email="testuser@statsig.com")
        user_two = StatsigUser("456", email="test@statsig.com")

        self.assertEqual(
            server.check_gate(user_one, "any_gate"),
            False
        )

        server.override_gate("any_gate", True, "123")

        self.assertEqual(
            server.check_gate(user_one, "any_gate"),
            True
        )

        self.assertEqual(
            server.check_gate(user_two, "any_gate"),
            False
        )

        server.override_gate("any_gate", False, "123")
        server.override_gate("any_gate", True, "456")

        self.assertEqual(
            server.check_gate(user_one, "any_gate"),
            False
        )

        self.assertEqual(
            server.check_gate(user_two, "any_gate"),
            True
        )

        # Global overrides respect user level overrides first
        server.override_gate("any_gate", True)
        self.assertEqual(
            server.check_gate(user_one, "any_gate"),
            False
        )
        self.assertEqual(
            server.check_gate(user_two, "any_gate"),
            True
        )
        self.assertEqual(
            server.check_gate(StatsigUser("4123980"), "any_gate"),
            True
        )

    def test_override_all(self):
        options = StatsigOptions(local_mode=True)
        server = StatsigServer()
        server.initialize("secret-key", options)

        user_one = StatsigUser("123", email="testuser@statsig.com")
        user_two = StatsigUser("456", email="test@statsig.com")

        self.assertEqual(
            server.check_gate(user_one, "any_gate"),
            False
        )

        self.assertEqual(
            server.check_gate(user_two, "any_gate"),
            False
        )

        server.override_gate("any_gate", True)

        self.assertEqual(
            server.check_gate(user_one, "any_gate"),
            True
        )

        self.assertEqual(
            server.check_gate(user_two, "any_gate"),
            True
        )

        server.override_experiment("my_experiment", {"test": False})

        self.assertEqual(
            server.get_experiment(user_one, "my_experiment").get_value(),
            {"test": False}
        )

        self.assertEqual(
            server.get_experiment(user_two, "my_experiment").get_value(),
            {"test": False}
        )

    def test_override_config(self):
        options = StatsigOptions(local_mode=True)
        server = StatsigServer()
        server.initialize("secret-key", options)

        user_one = StatsigUser("123", email="testuser@statsig.com")
        user_two = StatsigUser("456", email="test@statsig.com")

        self.assertEqual(
            server.get_config(user_one, "config").get_value(),
            {}
        )

        self.assertEqual(
            server.get_config(user_two, "config").get_value(),
            {}
        )

        override = {"test": 123}
        server.override_config("config", override, "123")

        self.assertEqual(
            server.get_config(user_one, "config").get_value(),
            override
        )

        self.assertEqual(
            server.get_config(user_two, "config").get_value(),
            {}
        )

        server.override_experiment("config", {}, "123")
        new_override = {"abc": "def"}
        server.override_experiment("config", new_override, "456")

        self.assertEqual(
            server.get_config(user_one, "config").get_value(),
            {}
        )

        self.assertEqual(
            server.get_config(user_two, "config").get_value(),
            new_override
        )

        # Global overrides respect user level overrides first
        new_override_2 = {"123": "ttt"}
        server.override_config("config", new_override_2)

        self.assertEqual(
            server.get_config(user_one, "config").get_value(),
            {}
        )
        self.assertEqual(
            server.get_config(user_two, "config").get_value(),
            new_override
        )
        self.assertEqual(
            server.get_config(StatsigUser("anyuser"), "config").get_value(),
            new_override_2
        )
