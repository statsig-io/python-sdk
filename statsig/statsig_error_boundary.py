import traceback
import requests
from .statsig_errors import StatsigNameError, StatsigRuntimeError, StatsigValueError

from .statsig_options import StatsigOptions
from .diagnostics import Diagnostics, Key, Context
from . import globals

REQUEST_TIMEOUT = 20


class _StatsigErrorBoundary:
    endpoint = "https://statsigapi.net/v1/sdk_exception"
    _seen: set
    _api_key: str

    def __init__(self, is_silent=False):
        self._seen = set()
        self._is_silent = is_silent

    def set_statsig_options_and_metadata(
        self, statsig_options: StatsigOptions, statsig_metadata: dict
    ):
        self._options = statsig_options
        self._metadata = statsig_metadata

    def set_api_key(self, api_key):
        self._api_key = api_key

    def capture(self, tag: str, task, recover, extra: dict = None):
        markerID = None
        key = None
        configName = None
        try:
            configName = (
                extra["configName"]
                if extra is not None and "configName" in extra
                else None
            )
            key: Key = Key.fromStr(tag)
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

    def log_exception(self, tag: str, exception: Exception, extra: dict = None):
        try:
            if self._is_silent is False:
                globals.logger.warning("[Statsig]: An unexpected error occurred.")
                globals.logger.warning(traceback.format_exc())
            if hasattr(self._options, 'disable_all_logging') and self._options.disable_all_logging:
                return

            name = type(exception).__name__
            if self._api_key is None or name in self._seen:
                return
            self._seen.add(name)
            requests.post(
                self.endpoint,
                json={
                    "exception": type(exception).__name__,
                    "info": traceback.format_exc(),
                    "statsigMetadata": self._metadata,
                    "tag": tag,
                    "extra": extra,
                    "statsigOptions": self._options.get_logging_copy()
                    if isinstance(self._options, StatsigOptions)
                    else None,
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
            pass

    def _start_diagnostics(self, key, configName):
        if key is None:
            return None
        markerID = f"{key.value}_{Diagnostics.get_marker_count(Context.API_CALL.value)}"
        Diagnostics.mark().api_call(key).start(
            {"configName": configName, "markerID": markerID}
        )
        return markerID

    def _end_diagnostics(self, markerID, key, success, configName):
        if markerID is None or key is None:
            return
        Diagnostics.mark().api_call(key).end(
            {"markerID": markerID, "success": success, "configName": configName}
        )
