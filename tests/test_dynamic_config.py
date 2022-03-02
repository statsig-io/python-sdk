import unittest

from statsig import DynamicConfig


class TestDynamicConfig(unittest.TestCase):

    def test_getters(self):
        config = DynamicConfig({
            "str": "string",
            "num": 4,
            "bool": True,
            "arr": [17],
        }, "my_config", "default")

        self.assertEqual(config.get_name(), "my_config")
        self.assertEqual(config.rule_id, "default")

        self.assertEqual(config.get("str"), "string")
        self.assertEqual(config.get("num"), 4)
        self.assertEqual(config.get("bool"), True)
        self.assertEqual(config.get("arr"), [17])
        self.assertEqual(config.get("nonexistent"), None)

        self.assertEqual(config.get("str", "fallback"), "string")
        self.assertEqual(config.get("str", 33), "string")
        self.assertEqual(config.get("num", 7), 4)
        self.assertEqual(config.get("num", "str"), 4)
        self.assertEqual(config.get("bool", False), True)
        self.assertEqual(config.get("bool", "hello"), True)
        self.assertEqual(config.get("arr", ["test"]), [17])
        self.assertEqual(config.get("nonexistent", 42), 42)
        self.assertEqual(config.get("nonexistent", "hi"), "hi")

        self.assertEqual(config.get_typed("str", 17), 17)
        self.assertEqual(config.get_typed("num", "default"), "default")
        self.assertEqual(config.get_typed("bool", ["test"]), ["test"])
        self.assertEqual(config.get_typed("arr", 33), 33)
        self.assertEqual(config.get_typed("nonexistent", "hello"), "hello")

        # List types do not differentiate the type of the values in the list
        self.assertEqual(config.get_typed("arr", ["str_arr"]), [17])


if __name__ == '__main__':
    unittest.main()
