import traceback
import requests
from statsig.statsig_errors import StatsigNameError, StatsigRuntimeError, StatsigValueError

from statsig.statsig_metadata import _StatsigMetadata

REQUEST_TIMEOUT = 20


class _StatsigErrorBoundary:
    endpoint = "https://statsigapi.net/v1/sdk_exception"
    _seen: set
    _api_key: str

    def __init__(self, is_silent=False):
        self._seen = set()
        self._is_silent = is_silent

    def set_api_key(self, api_key):
        self._api_key = api_key

    def capture(self, task, recover):
        try:
            return task()
        except (StatsigValueError, StatsigNameError, StatsigRuntimeError) as e:
            raise e
        except Exception as e:
            if self._is_silent is False:
                print("[Statsig]: An unexpected error occurred.")
                traceback.print_exc()

            self.log_exception(e)
            return recover()

    def swallow(self, task):
        def empty_recover():
            return None

        self.capture(task, empty_recover)

    def log_exception(self, exception: Exception):
        try:
            name = type(exception).__name__
            if self._api_key is None or name in self._seen:
                return

            self._seen.add(name)
            meta = _StatsigMetadata.get()
            requests.post(self.endpoint, json={
                "exception": type(exception).__name__,
                "info": traceback.format_exc(),
                "statsigMetadata": _StatsigMetadata.get()
            }, headers={
                'Content-type': 'application/json',
                'STATSIG-API-KEY': self._api_key,
                'STATSIG-SDK-TYPE': meta["sdkType"],
                'STATSIG-SDK-VERSION': meta["sdkVersion"]
            }, timeout=REQUEST_TIMEOUT)
        except BaseException:
            pass
