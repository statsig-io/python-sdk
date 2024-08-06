import unittest

from statsig import _SDK_Configs


class TestSDKFlags(unittest.TestCase):

    def test_empty(self):
        self.assertEqual(_SDK_Configs.on("not_a_flag"), False)

    def test_malformed(self):
        _SDK_Configs.set_flags({"bad_flag": 1})
        self.assertEqual(_SDK_Configs.on("bad_flag"), False)

    def test_flag_set(self):
        _SDK_Configs.set_flags({"a_flag": True})
        self.assertEqual(_SDK_Configs.on("a_flag"), True)


if __name__ == '__main__':
    unittest.main()
