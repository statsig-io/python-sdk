import traceback
import requests
from .statsig_errors import StatsigNameError, StatsigRuntimeError, StatsigValueError

from .statsig_metadata import _StatsigMetadata
from . import globals

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

    def capture(self, tag: str, task, recover):
        try:
            return task()
        except (StatsigValueError, StatsigNameError, StatsigRuntimeError) as e:
            raise e
        except Exception as e:
            self.log_exception(tag, e)
            return recover()

    def swallow(self, tag: str, task):
        def empty_recover():
            return None

        self.capture(tag, task, empty_recover)

    def log_exception(self, tag: str, exception: Exception, extra: dict = None):
        try:
            if self._is_silent is False:
                globals.logger.warning("[Statsig]: An unexpected error occurred.")
                globals.logger.warning(traceback.format_exc())

            name = type(exception).__name__
            if self._api_key is None or name in self._seen:
                return

            self._seen.add(name)
            meta = _StatsigMetadata.get()
            requests.post(self.endpoint, json={
                "exception": type(exception).__name__,
                "info": traceback.format_exc(),
                "statsigMetadata": _StatsigMetadata.get(),
                "tag": tag,
                "extra": extra
            }, headers={
                'Content-type': 'application/json',
                'STATSIG-API-KEY': self._api_key,
                'STATSIG-SDK-TYPE': meta["sdkType"],
                'STATSIG-SDK-VERSION': meta["sdkVersion"]
            }, timeout=REQUEST_TIMEOUT)
        except BaseException:
            pass
