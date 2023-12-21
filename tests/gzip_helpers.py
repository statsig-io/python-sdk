import gzip
import io
import json


class GzipHelpers:
    def decode_body(data: dict, filterDiagnostics: bool = True) -> dict:
        if "json" in data:
            return data["json"]
        else:
            headers = data["headers"]
            body = data["data"]
            if "Content-Encoding" in headers and headers["Content-Encoding"] == "gzip":
                with gzip.GzipFile(fileobj=io.BytesIO(body), mode="rb") as f:
                    body = json.loads(f.read().decode("utf-8"))
                    if filterDiagnostics:
                        events = [
                            event
                            for event in body["events"]
                            if event["eventName"] != "statsig::diagnostics"
                        ]
                        body["events"] = events
                    return body
            else:
                return json.loads(body)
