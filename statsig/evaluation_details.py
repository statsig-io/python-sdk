import time
from enum import Enum


class EvaluationReason(str, Enum):
    network = "Network"
    local_override = "LocalOverride"
    unrecognized = "Unrecognized"
    uninitialized = "Uninitialized"
    bootstrap = "Bootstrap"
    data_adapter = "DataAdapter"
    unsupported = "Unsupported"
    error = "error"


class EvaluationDetails:
    reason: EvaluationReason
    config_sync_time: int
    init_time: int
    server_time: int

    def __init__(self, config_sync_time: int, init_time: int,
                 reason: EvaluationReason):
        self.config_sync_time = config_sync_time
        self.init_time = init_time
        self.reason = reason
        self.server_time = round(time.time() * 1000)
