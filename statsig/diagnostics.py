from typing import Optional, Dict
import time
import random
from enum import Enum
from .statsig_options import StatsigOptions


class Context(Enum):
    INITIALIZE = "initialize"
    CONFIG_SYNC = "config_sync"
    API_CALL = "api_call"
    LOG_EVENT = "log_event"


class Key(Enum):
    DOWNLOAD_CONFIG_SPECS = "download_config_specs"
    DATA_STORE_CONFIG_SPECS = "data_store_config_specs"
    BOOTSTRAP = "bootstrap"
    OVERALL = "overall"
    GET_ID_LIST = "get_id_list"
    GET_ID_LIST_SOURCES = "get_id_list_sources"
    CHECK_GATE = "check_gate"
    GET_CONFIG = "get_config"
    GET_EXPERIMENT = "get_experiment"
    GET_LAYER = "get_layer"

    @staticmethod
    def fromStr(key: str):
        if key == "check_gate":
            return Key.CHECK_GATE
        if key == "get_config":
            return Key.GET_CONFIG
        if key == "get_layer":
            return Key.GET_LAYER
        if key == "get_experiment":
            return Key.GET_EXPERIMENT
        return None


class Step(Enum):
    PROCESS = "process"
    NETWORK_REQUEST = "network_request"


class Action(Enum):
    START = "start"
    END = "end"


class SamplingRate(Enum):
    ID_LIST = "idlist"
    DCS = "dcs"
    INITIALIZE = "initialize"
    LOG_EVENT = "logevent"
    API_CALL = "api_call"


MAX_SAMPLING_RATE = 10000
DEFAULT_SAMPLING_RATE = 100


class Marker:
    context = None

    def __init__(
        self,
        key: Optional[Key] = None,
        action: Optional[Action] = None,
        timestamp: Optional[float] = None,
        step: Optional[Step] = None,
        statusCode: Optional[int] = None,
        success: Optional[bool] = None,
        url: Optional[str] = None,
        idListCount: Optional[int] = None,
        reason: Optional[str] = None,
        sdkRegion: Optional[str] = None,
        markerID: Optional[str] = None,
        attempt: Optional[int] = None,
        retryLimit: Optional[int] = None,
        isRetry: Optional[bool] = None,
        configName: Optional[str] = None,
        error: Optional[dict] = None,
        payloadSize: Optional[int] = None,
    ):
        self.key = key
        self.action = action
        self.timestamp = (time.time() * 1000) if timestamp is None else timestamp
        self.step = step
        self.statusCode = statusCode
        self.success = success
        self.url = url
        self.idListCount = idListCount
        self.reason = reason
        self.sdkRegion = sdkRegion
        self.markerID = markerID
        self.attempt = attempt
        self.retryLimit = retryLimit
        self.isRetry = isRetry
        self.configName = configName
        self.error = error
        self.payloadSize = payloadSize

    def to_dict(self) -> Dict:
        marker_dict = {
            "key": self.key.value if self.key is not None else None,
            "action": self.action.value if self.action is not None else None,
            "timestamp": self.timestamp,
            "step": self.step.value if self.step is not None else None,
            "statusCode": self.statusCode,
            "success": self.success,
            "url": self.url,
            "idListCount": self.idListCount,
            "reason": self.reason,
            "sdkRegion": self.sdkRegion,
            "markerID": self.markerID,
            "attempt": self.attempt,
            "retryLimit": self.retryLimit,
            "isRetry": self.isRetry,
            "configName": self.configName,
            "error": self.error,
            "payloadSize": self.payloadSize,
        }
        return {k: v for k, v in marker_dict.items() if v is not None}

    # Actions #

    def start(self, data=None):
        self.action = Action.START
        if data is not None:
            for key, value in data.items():
                setattr(self, key, value)
        return self

    def end(self, data=None):
        self.action = Action.END
        if data is not None:
            for key, value in data.items():
                setattr(self, key, value)
        return self

    # Select Step #

    def process(self):
        self.step = Step.PROCESS
        return self

    def network_request(self):
        self.step = Step.NETWORK_REQUEST
        return self

    # Select Keys #

    def download_config_specs(self):
        self.key = Key.DOWNLOAD_CONFIG_SPECS
        return self

    def data_store_config_specs(self):
        self.key = Key.DATA_STORE_CONFIG_SPECS
        return self

    def bootstrap(self):
        self.key = Key.BOOTSTRAP
        return self

    def overall(self):
        self.context = (
            Context.INITIALIZE
        )  # overall is only ever used in initialize
        self.key = Key.OVERALL
        return self

    def get_id_list(self):
        self.key = Key.GET_ID_LIST
        return self

    def get_id_list_sources(self):
        self.key = Key.GET_ID_LIST_SOURCES
        return self

    def api_call(self, key: Key):
        self.context = Context.API_CALL
        self.key = key
        return self

    def log_event(self):
        self.context = Context.LOG_EVENT
        return self


class Diagnostics:
    def __init__(self, markers=None):
        self.context_to_markers = markers or {
            Context.INITIALIZE: [],
            Context.CONFIG_SYNC: [],
            Context.LOG_EVENT: [],
            Context.API_CALL: [],
        }
        self.context = Context.INITIALIZE
        self.default_max_markers = 50
        self.maxMarkers = {
            context: self.default_max_markers for context in Context
        }

        self.sampling_rate = {
            SamplingRate.DCS.value: 100,
            SamplingRate.ID_LIST.value: 100,
            SamplingRate.INITIALIZE.value: 10000,
            SamplingRate.LOG_EVENT.value: 100,
            SamplingRate.API_CALL.value: 100,
        }
        self.disabled = False
        self.logger = None

    def set_diagnostics_enabled(self, disable_diagnostics: bool):
        self.disabled = disable_diagnostics
        return self

    def set_logger(self, logger):
        self.logger = logger
        return self

    def set_context(self, context: Context):
        self.context = context
        return self

    def add_marker(self, marker):
        context = marker.context if marker.context is not None else self.context
        if self.disabled and context == Context.API_CALL:
            return False
        max_markers = self.maxMarkers.get(context, self.default_max_markers)
        cur_length = len(self.context_to_markers[context])
        if max_markers <= cur_length:
            return False
        self.context_to_markers[context].append(marker)
        return True

    def set_max_markers(self, context, max_markers):
        self.maxMarkers[context] = max_markers

    def get_marker_count(self, context):
        return len(self.context_to_markers.get(context, []))

    def get_markers(self, context):
        return self.context_to_markers.get(context, [])

    def clear_context(self, context):
        self.context_to_markers[context] = []

    def log_diagnostics(self, context: Context, key: Optional[Key] = None):
        if self.logger is None or len(self.context_to_markers[context]) == 0:
            return

        metadata = {
            "markers": [
                marker.to_dict() for marker in self.context_to_markers[context]
            ],
            "context": context,
        }
        if context == Context.INITIALIZE:
            metadata["statsigOptions"] = (
                self.statsig_options.get_logging_copy()
                if isinstance(self.statsig_options, StatsigOptions)
                else None
            )
        self.clear_context(context)

        if self.should_log_diagnostics(context, key):
            self.logger.log_diagnostics_event(metadata)

    def set_sampling_rate(self, obj: dict):
        if not obj or not isinstance(obj, dict):
            return

        def safe_set(key, value):
            if not isinstance(value, (int, float)):
                return
            if value < 0:
                self.sampling_rate[key] = 0
            elif value > MAX_SAMPLING_RATE:
                self.sampling_rate[key] = MAX_SAMPLING_RATE
            else:
                self.sampling_rate[key] = int(value)

        for samplingRateKey in SamplingRate:
            safe_set(samplingRateKey.value, obj.get(samplingRateKey.value))

    def set_statsig_options(self, options: StatsigOptions):
        self.statsig_options = options

    def should_log_diagnostics(self, context: Context, key: Optional[Key] = None) -> bool:
        rand = random.random() * MAX_SAMPLING_RATE
        if context == Context.LOG_EVENT:
            return rand < self.sampling_rate.get(SamplingRate.LOG_EVENT.value, 0)
        if context == Context.INITIALIZE:
            return rand < self.sampling_rate.get(SamplingRate.INITIALIZE.value, 0)
        if context == Context.API_CALL:
            return rand < self.sampling_rate.get(SamplingRate.API_CALL.value, 0)
        if key in (Key.GET_ID_LIST.value, Key.GET_ID_LIST_SOURCES.value):
            return rand < self.sampling_rate.get(SamplingRate.ID_LIST.value, 0)
        if key == Key.DOWNLOAD_CONFIG_SPECS.value:
            return rand < self.sampling_rate.get(SamplingRate.DCS.value, 0)
        return rand < DEFAULT_SAMPLING_RATE  # error in code

    @staticmethod
    def format_error(e: Exception):
        if e is None:
            return None
        return {
            "name": type(e).__name__,
        }
