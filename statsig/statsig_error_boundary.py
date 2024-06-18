from concurrent.futures import ThreadPoolExecutor
from typing import Optional
import traceback
import requests
from .statsig_errors import StatsigNameError, StatsigRuntimeError, StatsigValueError

from .statsig_options import StatsigOptions
from .diagnostics import Diagnostics, Key, Context, Marker
from . import globals

REQUEST_TIMEOUT = 5

class _StatsigErrorBoundary:
    endpoint = "https://statsigapi.net/v1/sdk_exception"
    _seen: set
    _api_key: str

    def __init__(self, is_silent=False):
        self._seen = set()
        self._is_silent = is_silent
        self._executor = ThreadPoolExecutor(max_workers=1)

    def set_statsig_options_and_metadata(
        self, statsig_options: StatsigOptions, statsig_metadata: dict
    ):
        self._options = statsig_options
        self._metadata = statsig_metadata

    def set_diagnostics(self, diagnostics: Diagnostics):
        self._diagnostics = diagnostics

    def set_api_key(self, api_key):
        self._api_key = api_key

    def capture(self, tag: str, task, recover, extra: Optional[dict] = None):
        markerID = None
        key = None
        configName = None
        try:
            configName = (
                extra["configName"]
                if extra is not None and "configName" in extra
                else None
            )
            key = Key.fromStr(tag)
            markerID = self._start_diagnostics(key, configName)
            result = task()
            self._end_diagnostics(markerID, key, True, configName)
            return result
        except (StatsigValueError, StatsigNameError, StatsigRuntimeError) as e:
            raise e
        except Exception as e:
            self.log_exception(tag, e, extra)
            self._end_diagnostics(markerID, key, False, configName)
            return recover()

    def swallow(self, tag: str, task):
        def empty_recover():
            return None

        self.capture(tag, task, empty_recover)

    def shutdown(self, wait=False):
        self._executor.shutdown(wait)

    def log_exception(
        self,
        tag: str,
        exception: Exception,
        extra: Optional[dict] = None,
        bypass_dedupe: bool = False,
    ):
        try:
            if self._is_silent is False:
                globals.logger.warning("[Statsig]: An unexpected error occurred.")
                stack_trace = traceback.format_exc().replace(self._api_key, "********")
                globals.logger.warning(stack_trace)
            if (
                hasattr(self._options, "disable_all_logging")
                and self._options.disable_all_logging
            ):
                return

            name = type(exception).__name__
            if self._api_key is None:
                return
            if bypass_dedupe is False and name in self._seen:
                return
            self._seen.add(name)

            self._executor.submit(
                self._post_exception,
                name,
                traceback.format_exc(),
                tag,
                extra,
            )
        except BaseException:
            # no-op, best effort
            pass

    def _post_exception(self, name, info, tag, extra):
        try:
            requests.post(
                self.endpoint,
                json={
                    "exception": name,
                    "info": info,
                    "statsigMetadata": self._metadata,
                    "tag": tag,
                    "extra": extra,
                    "statsigOptions": (
                        self._options.get_logging_copy() if isinstance(self._options, StatsigOptions) else None
                    ),
                },
                headers={
                    "Content-type": "application/json",
                    "STATSIG-API-KEY": self._api_key,
                    "STATSIG-SDK-TYPE": self._metadata["sdkType"],
                    "STATSIG-SDK-VERSION": self._metadata["sdkVersion"],
                },
                timeout=REQUEST_TIMEOUT,
            )
        except BaseException:
            # no-op, best effort
            pass

    def _start_diagnostics(self, key, configName):
        try:
            if key is None:
                return None
            markerID = (
                f"{key.value}_{self._diagnostics.get_marker_count(Context.API_CALL)}"
            )
            self._diagnostics.add_marker(Marker().api_call(key).start(
                {"configName": configName, "markerID": markerID}
            ))
            return markerID
        except BaseException:
            return None

    def _end_diagnostics(self, markerID, key, success, configName):
        try:
            if markerID is None or key is None:
                return
            self._diagnostics.add_marker(Marker().api_call(key).end(
                {"markerID": markerID, "success": success, "configName": configName}
            ))
        except BaseException:
            pass
