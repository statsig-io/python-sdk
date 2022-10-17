from typing import Callable, Union
from urllib.parse import urlparse, ParseResult


class NetworkStub:
    host: str

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

    def __init__(self, host: str):
        self.host = host
        self._stubs = {}

    def reset(self):
        self._stubs = {}

    def stub_request_with_value(self, path, response_code: int, response_body: Union[dict, str]):
        if not isinstance(response_body, dict) and not isinstance(response_body, str):
            raise "Must provide a dictionary or string"

        self._stubs[path] = {
            "response_code": response_code,
            "response_body": response_body,
        }

    def stub_request_with_function(self, path, response_code: int,
                                   response_func: Callable[[str, dict], object]):
        if not callable(response_func):
            raise "Must provide a function"

        self._stubs[path] = {
            "response_code": response_code,
            "response_func": response_func
        }

    def mock(*args, **kwargs):
        instance: NetworkStub = args[0]
        url: ParseResult = urlparse(args[1])

        if (url.scheme + "://" + url.hostname) != instance.host:
            return

        paths = list(instance._stubs.keys())
        for path in paths:
            stub_data: dict = instance._stubs[path]

            if url.path.endswith(path):
                response_body = stub_data.get("response_body", None)
                if stub_data.get("response_func", None) is not None:
                    response_body = stub_data["response_func"](url, kwargs)

                headers = {}
                if isinstance(response_body, str):
                    headers["content-length"] = len(response_body)

                return NetworkStub.StubResponse(stub_data["response_code"], response_body, headers)

        return NetworkStub.StubResponse(404)
