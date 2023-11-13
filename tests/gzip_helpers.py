import gzip
import io
import json

class GzipHelpers:
    def decode_body(data: dict) -> dict:
        if "json" in data:
            return data["json"]
        else:
            headers = data["headers"]
            body = data["data"]
            if "Content-Encoding" in headers and headers["Content-Encoding"] == "gzip":
                with gzip.GzipFile(fileobj=io.BytesIO(body), mode="rb") as f:
                    return json.loads(f.read().decode("utf-8"))
            else:
                return json.loads(body)
