import re
from typing import Callable, Union
from urllib.parse import urlparse, ParseResult

STATSIG_APIS = ["https://api.statsigcdn.com/", "https://statsigapi.net/"]

class NetworkStub:
    host: str
    mock_statsig_api: bool

    class StubResponse:
        def __init__(self, status, data=None, headers=None):
            if headers is None:
                headers = {}

            self.status_code = status
            self.ok = True
            self.headers = headers
            self._json = data
            self.text = data

        def json(self):
            return self._json

    def __init__(self, host: str, mock_statsig_api = False):
        self.host = host
        self.mock_statsig_api = mock_statsig_api
        self._stubs = {}

    def reset(self):
        self._stubs = {}

    def stub_request_with_value(
            self, path, response_code: int, response_body: Union[dict, str]):
        if not isinstance(response_body, dict) and not isinstance(
                response_body, str):
            raise "Must provide a dictionary or string"

        self._stubs[path] = {
            "response_code": response_code,
            "response_body": response_body,
        }

    def stub_request_with_function(self, path, response_code: Union[int, Callable[[str, dict], int]],
                                   response_func: Callable[[str, dict], object]):
        if not callable(response_func):
            raise "Must provide a function"

        self._stubs[path] = {
            "response_code": response_code,
            "response_func": response_func
        }

    def mock(*args, **kwargs):
        instance: NetworkStub = args[0]
        method: str = args[1]
        url: ParseResult = urlparse(args[2])
        request_host = (url.scheme + "://" + url.hostname)
        if request_host != instance.host and (instance.mock_statsig_api and request_host not in STATSIG_APIS):
            return

        paths = list(instance._stubs.keys())
        for path in paths:
            stub_data: dict = instance._stubs[path]
            
            if re.search(f".*{path}", url.path) is not None:
                response_body = stub_data.get("response_body", None)
                if stub_data.get("response_func", None) is not None:
                    response_body = stub_data["response_func"](url, **kwargs)
                response_code = stub_data.get("response_code", None)
                if callable(response_code):
                    response_code = response_code(url, kwargs)

                headers = {}
                if isinstance(response_body, str):
                    headers["content-length"] = len(response_body)

                return NetworkStub.StubResponse(
                    stub_data["response_code"], response_body, headers)

        return NetworkStub.StubResponse(404)
