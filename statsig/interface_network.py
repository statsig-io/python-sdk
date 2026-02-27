from enum import Enum
from typing import Optional, Callable, Any


class NetworkProtocol(Enum):
    HTTP = "http"
    GRPC = "grpc"
    GRPC_WEBSOCKET = "grpc_websocket"


class NetworkEndpoint(Enum):
    LOG_EVENT = "log_event"
    DOWNLOAD_CONFIG_SPECS = "download_config_specs"
    GET_ID_LISTS = "get_id_lists"
    ALL = "all"


class IStreamingListeners:
    def __init__(self, on_update: Callable, on_error: Callable):
        self.on_update = on_update
        self.on_error = on_error


class IStreamingFallback:
    def __init__(self):
        self.started = False

    def backup_started(self):
        return self.started

    def start_backup(self):
        pass

    def cancel_backup(self):
        pass


class IStatsigNetworkWorker:
    @property
    def type(self) -> NetworkProtocol:
        return NetworkProtocol.HTTP

    def is_pull_worker(self) -> bool:
        return True

    def get_dcs(
            self,
            on_complete: Callable,
            since_time: int = 0,
            log_on_exception: Optional[bool] = False,
            init_timeout: Optional[int] = None,
    ):
        pass

    def get_id_lists(
            self,
            on_complete: Callable,
            log_on_exception: Optional[bool] = False,
            init_timeout: Optional[int] = None,
    ):
        pass

    def get_id_list(self, on_complete: Any, url, headers, log_on_exception=False):
        pass

    def log_events(self, payload, headers=None, log_on_exception=False, retry=0):
        pass

    def get_dcs_fallback(
            self,
            on_complete: Callable,
            since_time: int = 0,
            log_on_exception: Optional[bool] = False,
            init_timeout: Optional[int] = None,
    ):
        pass

    def get_id_lists_fallback(
            self,
            on_complete: Any,
            log_on_exception: Optional[bool] = False,
            init_timeout: Optional[int] = None,
    ):
        pass

    def spawn_bg_threads_if_needed(self):
        pass

    def shutdown(self) -> None:
        pass


class IStatsigWebhookWorker:
    def start_listen_for_config_spec(self, listeners: IStreamingListeners) -> None:
        pass

    def start_listen_for_id_list(self, listeners: IStreamingListeners) -> None:
        pass

    def register_fallback_cb(self, cb: Optional[IStreamingFallback]) -> None:
        self.backup_callbacks = cb

    def config_spec_listening_started(self) -> bool:
        return False

    def id_list_listening_started(self) -> bool:
        return False
