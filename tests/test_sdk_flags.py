import unittest

from statsig import _SDKFlags


class TestSDKFlags(unittest.TestCase):

    def test_empty(self):
        self.assertEqual(_SDKFlags.on("not_a_flag"), False)

    def test_malformed(self):
        _SDKFlags.set_flags({"bad_flag": 1})
        self.assertEqual(_SDKFlags.on("bad_flag"), False)

    def test_flag_set(self):
        _SDKFlags.set_flags({"a_flag": True})
        self.assertEqual(_SDKFlags.on("a_flag"), True)


if __name__ == '__main__':
    unittest.main()
