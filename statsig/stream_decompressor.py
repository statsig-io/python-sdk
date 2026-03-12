import zlib
import gzip
import brotli


class StreamDecompressor:
    def __init__(self, raw, encoding):
        self.raw = raw
        self.encoding = encoding
        self.stream = self

        if encoding == "gzip":
            self.gzip_decompressor = gzip.GzipFile(fileobj=raw)
        elif encoding == "br":
            self.brotli_decompressor = brotli.Decompressor()
        elif encoding == "deflate":
            self.deflate_decompressor = zlib.decompressobj()
        else:
            self.stream = self.raw

    def read(self, size=-1):
        if self.encoding == "gzip":
            return self.gzip_decompressor.read(size)

        if self.encoding == "br":
            return self.brotli_decompressor.process(self.raw.read(size))

        if self.encoding == "deflate":
            return self.deflate_decompressor.decompress(self.raw.read(size))

        return self.raw.read(size)
