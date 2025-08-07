import unittest
from statsig.stream_decompressor import StreamDecompressor
import ijson
import os
import io


def get_file_stream(file_name):
    path = os.path.join(os.path.dirname(__file__), "../testdata", file_name)
    file = open(path, "rb")
    return io.BufferedReader(file)


class TestStreamDecompressor(unittest.TestCase):

    def test_empty(self):
        with get_file_stream("dcs_plain_text") as stream:
            decompressor = StreamDecompressor(stream, None)

            keys = []
            for k, _v in ijson.kvitems(decompressor, ""):
                keys.append(k)

        self.assertIn("feature_gates", keys)
        self.assertIn("dynamic_configs", keys)
        self.assertIn("layer_configs", keys)

    def test_gzip(self):
        with get_file_stream("dcs_gzip") as stream:
            decompressor = StreamDecompressor(stream, "gzip")

            keys = []
            for k, _v in ijson.kvitems(decompressor, ""):
                keys.append(k)

        self.assertIn("feature_gates", keys)
        self.assertIn("dynamic_configs", keys)
        self.assertIn("layer_configs", keys)

    def test_deflate(self):
        with get_file_stream("dcs_deflate") as stream:
            decompressor = StreamDecompressor(stream, "deflate")

            keys = []
            for k, _v in ijson.kvitems(decompressor, ""):
                keys.append(k)

        self.assertIn("feature_gates", keys)
        self.assertIn("dynamic_configs", keys)
        self.assertIn("layer_configs", keys)

    def test_brotli(self):
        with get_file_stream("dcs_brotli") as stream:
            decompressor = StreamDecompressor(stream, "br")

            keys = []
            for k, _v in ijson.kvitems(decompressor, ""):
                keys.append(k)

        self.assertIn("feature_gates", keys)
        self.assertIn("dynamic_configs", keys)
        self.assertIn("layer_configs", keys)


if __name__ == "__main__":
    unittest.main()
