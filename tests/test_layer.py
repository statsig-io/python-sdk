import unittest

from statsig import Layer
from statsig.evaluation_details import EvaluationDetails, EvaluationReason


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

        self.assertDictEqual(layer.get_values(), {
            "str": "string",
            "num": 4,
            "bool": True,
            "arr": [17],
        })

        # List types do not differentiate the type of the values in the list
        self.assertEqual(layer.get_typed("arr", ["str_arr"]), [17])

    def test_evaluation_details(self):
        layer = Layer._create('network', {
            "str": "string",
            "num": 4,
            "bool": True,
            "arr": [17],
        }, "default", evaluation_details=EvaluationDetails(123, 123,
                                                           EvaluationReason.network))

        self.assertEqual(layer.get_evaluation_details().config_sync_time, 123)
        self.assertEqual(layer.get_evaluation_details().reason, EvaluationReason.network)

        layer = Layer._create('no_eval', {
            "str": "string",
            "num": 4,
            "bool": True,
            "arr": [17],
        }, "default", evaluation_details=None)

        self.assertEqual(layer.get_evaluation_details(), None)

        layer = Layer._create('uninitialized', {
            "str": "string",
            "num": 4,
            "bool": True,
            "arr": [17],
        }, "default", evaluation_details=EvaluationDetails(123, 123, EvaluationReason.uninitialized))

        self.assertEqual(layer.get_evaluation_details().config_sync_time, 123)
        self.assertEqual(layer.get_evaluation_details().reason, EvaluationReason.uninitialized)

        layer = Layer._create('error', {
            "str": "string",
            "num": 4,
            "bool": True,
            "arr": [17],
        }, "default", evaluation_details=EvaluationDetails(123, 123, EvaluationReason.error))

        self.assertEqual(layer.get_evaluation_details().config_sync_time, 123)
        self.assertEqual(layer.get_evaluation_details().reason, EvaluationReason.error)


if __name__ == '__main__':
    unittest.main()
