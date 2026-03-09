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


class HttpxRawReader:
    def __init__(self, response, chunk_size: int = 8192):
        self._iterator = iter(response.iter_raw(chunk_size))
        self._buffer = b""

    def read(self, size=-1):
        if size == 0:
            return b""

        if size is None or size < 0:
            chunks = []
            if self._buffer:
                chunks.append(self._buffer)
                self._buffer = b""
            chunks.extend(self._iterator)
            return b"".join(chunks)

        while len(self._buffer) < size:
            try:
                chunk = next(self._iterator)
                if not chunk:
                    break
                self._buffer += chunk
            except StopIteration:
                break

        result = self._buffer[:size]
        self._buffer = self._buffer[size:]
        return result
