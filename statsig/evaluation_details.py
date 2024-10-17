import time
from enum import Enum


class EvaluationReason(str, Enum):
    local_override = "LocalOverride"
    unrecognized = "Unrecognized"
    unsupported = "Unsupported"
    error = "error"
    none = "none"


class DataSource(str, Enum):
    DATASTORE = "DataAdapter"
    BOOTSTRAP = "Bootstrap"
    NETWORK = "Network"
    STATSIG_NETWORK = "StatsigNetwork"
    UNINITIALIZED = "Uninitialized"


class EvaluationDetails:
    reason: EvaluationReason
    source: DataSource
    config_sync_time: int
    init_time: int
    server_time: int

    def __init__(self, config_sync_time: int, init_time: int,
                 source: DataSource, reason: EvaluationReason = EvaluationReason.none):
        self.config_sync_time = config_sync_time
        self.init_time = init_time
        self.reason = reason
        self.source = source
        self.server_time = round(time.time() * 1000)

    def detailed_reason(self):
        if self.reason == EvaluationReason.none:
            return f"{self.source}"
        return f"{self.source}:{self.reason}"
