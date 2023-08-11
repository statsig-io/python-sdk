from typing import Dict
import time
import random
from enum import Enum

from .statsig_logger import _StatsigLogger

class Context(Enum):
    INITIALIZE = "initialize"
    CONFIG_SYNC = "config_sync"
    API_CALL = "api_call"
    LOG_EVENT = "log_event"


class Key(Enum):
    DOWNLOAD_CONFIG_SPECS = "download_config_specs"
    BOOTSTRAP = "bootstrap"
    OVERALL = "overall"
    GET_ID_LIST = "get_id_list"
    GET_ID_LIST_SOURCES = "get_id_list_sources"
    CHECK_GATE = "check_gate"
    GET_CONFIG = "get_config"
    GET_EXPERIMENT = "get_experiment"
    GET_LAYER = "get_layer"


class Step(Enum):
    PROCESS = "process"
    NETWORK_REQUEST = "network_request"


class Action(Enum):
    START = "start"
    END = "end"

class SamplingRate(Enum):
    ID_LIST = "idlist"
    DCS = 'dcs'
    INITIALIZE = 'initialize'
    LOG_EVENT = 'logevent'


MAX_SAMPLING_RATE = 10000
DEFAULT_SAMPLING_RATE = 100


class Marker:
    context = None

    def __init__(self,
                 key: Key = None,
                 action: Action = None,
                 timestamp: float = None,
                 step: Step = None,
                 statusCode: int = None,
                 success: bool = None,
                 url: str = None,
                 idListCount: int = None,
                 reason: str = None,
                 sdkRegion: str = None,
                 markerID: str = None,
                 attempt: int = None,
                 retryLimit: int = None,
                 isRetry: bool = None,
                 configName: str = None):
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

        }
        return {k: v for k, v in marker_dict.items() if v is not None}

    # Actions #

    def start(self, data=None):
        self.action = Action.START
        if data is not None:
            for key, value in data.items():
                setattr(self, key, value)
        return Diagnostics.add_marker(self)

    def end(self, data=None):
        self.action = Action.END
        if data is not None:
            for key, value in data.items():
                setattr(self, key, value)
        return Diagnostics.add_marker(self)

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

    def bootstrap(self):
        self.key = Key.BOOTSTRAP
        return self

    def overall(self):
        self.context = Context.INITIALIZE.value  # overall is only ever used in initialize
        self.key = Key.OVERALL
        return self

    def get_id_list(self):
        self.key = Key.GET_ID_LIST
        return self

    def get_id_list_sources(self):
        self.key = Key.GET_ID_LIST_SOURCES
        return self


class DiagnosticsImpl:
    def __init__(self, markers=None):
        self.context_to_markers = markers or {
            "initialize": [],
            "config_sync": [],
            "event_logging": [],
            "error_boundary": []
        }
        self.context = "initialize"
        self.default_max_markers = 50
        self.maxMarkers = {context.value: self.default_max_markers for context in Context}

        self.sampling_rate = {
            SamplingRate.DCS.value: 100,
            SamplingRate.ID_LIST.value: 100,
            SamplingRate.INITIALIZE.value: 10000,
            SamplingRate.LOG_EVENT.value: 100
        }
        self.disabled = False
        self.logger = None

    def set_diagnostics_enabled(self, disable_diagnostics: bool):
        self.disabled = disable_diagnostics
        return self

    def set_logger(self, logger: _StatsigLogger):
        self.logger = logger
        return self

    def mark(self):
        return Marker()

    def set_context(self, context: Context):
        self.context = context
        return self

    def add_marker(self, marker):
        if self.disabled:
            return False
        context = marker.context if marker.context is not None else self.context
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

    def clear_context(self, context):
        self.context_to_markers[context] = []

    def log_diagnostics(self, context: Context, key: Key = None):
        if self.disabled is True or self.logger is None or len(self.context_to_markers[context]) == 0:
            return
        metadata = {
            "markers": [marker.to_dict() for marker in self.context_to_markers[context]],
            "context": context,
        }
        self.clear_context(context)

        if self._should_log_diagnostics(context, key):
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
                self.sampling_rate[key] = value

        for samplingRateKey in SamplingRate:
            safe_set(samplingRateKey.value, obj.get(samplingRateKey.value))

    def _should_log_diagnostics(self, context: Context, key: Key) -> bool:
        rand = random.random() * MAX_SAMPLING_RATE

        if context == Context.LOG_EVENT.value:
            return rand < self.sampling_rate.get(SamplingRate.LOG_EVENT.value, 0)
        if context == Context.INITIALIZE.value:
            return rand < self.sampling_rate.get(SamplingRate.INITIALIZE.value, 0)
        if key in (Key.GET_ID_LIST.value, Key.GET_ID_LIST_SOURCES.value):
            return rand < self.sampling_rate.get(SamplingRate.ID_LIST.value, 0)
        if key == Key.DOWNLOAD_CONFIG_SPECS.value:
            return rand < self.sampling_rate.get(SamplingRate.DCS.value, 0)
        return rand < DEFAULT_SAMPLING_RATE  # error in code


class Diagnostics:
    instance = None

    @staticmethod
    def initialize():
        Diagnostics.instance = DiagnosticsImpl()
        Diagnostics.set_diagnostics_enabled = Diagnostics.instance.set_diagnostics_enabled
        Diagnostics.set_logger = Diagnostics.instance.set_logger
        Diagnostics.mark = Diagnostics.instance.mark
        Diagnostics.add_marker = Diagnostics.instance.add_marker
        Diagnostics.get_marker_count = Diagnostics.instance.get_marker_count
        Diagnostics.set_max_markers = Diagnostics.instance.set_max_markers
        Diagnostics.set_context = Diagnostics.instance.set_context
        Diagnostics.clear_context = Diagnostics.instance.clear_context
        Diagnostics.log_diagnostics = Diagnostics.instance.log_diagnostics
        Diagnostics.set_sampling_rate = Diagnostics.instance.set_sampling_rate
