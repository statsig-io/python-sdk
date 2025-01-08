import gzip
import io
import json
import re
from io import BytesIO
from typing import Callable, Union, Optional
from urllib.parse import urlparse, ParseResult

from requests import HTTPError
from urllib3.exceptions import IncompleteRead

STATSIG_APIS = ["https://api.statsigcdn.com", "https://statsigapi.net"]


class NetworkStub:
    host: str
    mock_statsig_api: bool

    class StubResponse:
        def __init__(self, status, data=None, headers=None, raw=None, url=None, options=None):
            if headers is None:
                headers = {}

            self.status_code = status
            self.ok = 200 <= status < 300
            self.headers = headers
            self.text = data
            self.url = url or "http://localhost"
            self.raw = None
            self._raw = raw
            self._json = data
            self._options = options or {}
            self.set_raw()

        def json(self):
            return self._json

        def set_raw(self):
            if self._options.get("incompleteRead", False):
                raise IncompleteRead(partial=237981, expected=384930)
            self.raw = self._raw

        def raise_for_status(self):
            if not self.ok:
                raise HTTPError(f"{self.status_code} raise for status error")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    def __init__(self, host: str, mock_statsig_api=False):
        self.host = host
        self.mock_statsig_api = mock_statsig_api
        self._stubs = {}
        self._statsig_stubs = {}

    def reset(self):
        self._stubs = {}

    def stub_request_with_value(
            self, path, response_code: int, response_body: Union[dict, str], headers: Optional[dict] = None,
            options=None):
        if not isinstance(response_body, dict) and not isinstance(response_body, str):
            raise "Must provide a dictionary or string"

        self._stubs[path] = {
            "response_code": response_code,
            "response_body": response_body,
            "headers": headers or {},
            "options": options or {}
        }

    def stub_request_with_function(self, path, response_code: Union[int, Callable[[str, dict], int]],
                                   response_func: Callable[[str, dict], object], headers: Optional[dict] = None,
                                   options=None):
        if not callable(response_func):
            raise "Must provide a function"

        self._stubs[path] = {
            "response_code": response_code,
            "response_func": response_func,
            "headers": headers or {},
            "options": options or {}
        }

    def stub_statsig_api_request_with_value(
            self, path, response_code: int, response_body: Union[dict, str], headers: Optional[dict] = None,
            options=None):
        if not isinstance(response_body, dict) and not isinstance(response_body, str):
            raise "Must provide a dictionary or string"

        self._statsig_stubs[path] = {
            "response_code": response_code,
            "response_body": response_body,
            "headers": headers or {},
            "options": options or {}
        }

    def stub_statsig_api_request_with_function(self, path, response_code: Union[int, Callable[[str, dict], int]],
                                               response_func: Callable[[str, dict], object],
                                               headers: Optional[dict] = None, options=None):
        if not callable(response_func):
            raise "Must provide a function"

        self._statsig_stubs[path] = {
            "response_code": response_code,
            "response_func": response_func,
            "headers": headers or {},
            "options": options or {}
        }

    def mock(*args, **kwargs):
        instance: NetworkStub = args[0]
        method: str = args[1]
        url: ParseResult = urlparse(args[2])
        request_host = f"{url.scheme}://{url.hostname}"

        if not instance.mock_statsig_api and request_host != instance.host or (
                instance.mock_statsig_api and (request_host != instance.host and request_host not in STATSIG_APIS)):
            return

        stubs = instance._statsig_stubs if request_host in STATSIG_APIS and instance.mock_statsig_api else instance._stubs
        for path, stub_data in stubs.items():
            if re.search(f".*{path}", url.path):
                response_body = stub_data.get("response_body")
                headers = stub_data.get("headers", {})
                options = stub_data.get("options", {})

                if "response_func" in stub_data:
                    response_body = stub_data["response_func"](url, **kwargs)

                response_code = stub_data.get("response_code")
                if callable(response_code):
                    response_code = response_code(url, kwargs)

                if "Content-Encoding" in headers and headers["Content-Encoding"] == "gzip":
                    response_body = gzip_compress(response_body)

                if isinstance(response_body, str):
                    headers["content-length"] = len(response_body)
                    byte_body = response_body.encode("utf-8")
                else:
                    byte_body = json.dumps(response_body).encode("utf-8")

                try:
                    raw = io.BytesIO(byte_body)
                except Exception as e:
                    print(f"Error in creating raw response: {e}")
                    raw = None

                return NetworkStub.StubResponse(response_code, response_body, headers, raw, options=options)

        return NetworkStub.StubResponse(404)


def gzip_compress(data: Union[str, bytes]) -> bytes:
    if isinstance(data, str):
        data = data.encode('utf-8')
    buf = BytesIO()
    with gzip.GzipFile(fileobj=buf, mode='wb') as gz:
        gz.write(data)
    return buf.getvalue()
