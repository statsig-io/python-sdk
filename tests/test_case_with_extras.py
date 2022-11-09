import unittest


class TestCaseWithExtras(unittest.TestCase):

    def assertSubsetOf(self, subset: dict, full: dict):
        for key in subset:
            self.assertEqual(subset[key], full[key])
