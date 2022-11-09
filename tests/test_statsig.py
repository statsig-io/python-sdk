import unittest
from statsig import __version__
from statsig.statsig_metadata import _StatsigMetadata


class TestStatsig(unittest.TestCase):
    def test_version(self):
        metadata = _StatsigMetadata.get()
        self.assertEqual(__version__, metadata["sdkVersion"])
