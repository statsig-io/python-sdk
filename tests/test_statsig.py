import unittest
from statsig import __version__, statsig
from statsig.statsig_metadata import _StatsigMetadata


class TestStatsig(unittest.TestCase):
    def test_version(self):
        metadata = _StatsigMetadata.get()
        self.assertEqual(__version__, metadata["sdkVersion"])

    def test_initialize_without_options(self):
        try:
            statsig.initialize("secret-key")
        except:
            self.fail("initialize with no options failed")

        statsig.shutdown()
