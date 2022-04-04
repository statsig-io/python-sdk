import unittest

from statsig import Layer


class TestLayer(unittest.TestCase):

    def test_getters(self):
        layer = Layer._create('my_layer', {
            "str": "string",
            "num": 4,
            "bool": True,
            "arr": [17],
        }, "default")

        self.assertEqual(layer.get_name(), "my_layer")
        self.assertEqual(layer.rule_id, "default")

        self.assertEqual(layer.get("str"), "string")
        self.assertEqual(layer.get("num"), 4)
        self.assertEqual(layer.get("bool"), True)
        self.assertEqual(layer.get("arr"), [17])
        self.assertEqual(layer.get("nonexistent"), None)

        self.assertEqual(layer.get("str", "fallback"), "string")
        self.assertEqual(layer.get("str", 33), "string")
        self.assertEqual(layer.get("num", 7), 4)
        self.assertEqual(layer.get("num", "str"), 4)
        self.assertEqual(layer.get("bool", False), True)
        self.assertEqual(layer.get("bool", "hello"), True)
        self.assertEqual(layer.get("arr", ["test"]), [17])
        self.assertEqual(layer.get("nonexistent", 42), 42)
        self.assertEqual(layer.get("nonexistent", "hi"), "hi")

        self.assertEqual(layer.get_typed("str", 17), 17)
        self.assertEqual(layer.get_typed("num", "default"), "default")
        self.assertEqual(layer.get_typed("bool", ["test"]), ["test"])
        self.assertEqual(layer.get_typed("arr", 33), 33)
        self.assertEqual(layer.get_typed("nonexistent", "hello"), "hello")

        # List types do not differentiate the type of the values in the list
        self.assertEqual(layer.get_typed("arr", ["str_arr"]), [17])


if __name__ == '__main__':
    unittest.main()
