import threading
from typing import Any, Callable, Optional

from .thread_util import spawn_background_thread

from .statsig_options import (
    DEFAULT_RULESET_SYNC_INTERVAL,
    StatsigOptions,
    STATSIG_CDN,
    STATSIG_API,
)
from .diagnostics import Diagnostics
from .grpc_websocket_worker import GRPCWebsocketWorker
from .grpc_worker import GRPCWorker
from .globals import logger
from .http_worker import HttpWorker
from .interface_network import (
    IStreamingFallback,
    IStreamingListeners,
    NetworkProtocol,
    NetworkEndpoint,
    IStatsigNetworkWorker,
    IStatsigWebhookWorker,
)
from .statsig_error_boundary import _StatsigErrorBoundary


class StreamingFallback(IStreamingFallback):
    def __init__(
        self, fn: Callable, interval: int, name: str, eb: _StatsigErrorBoundary
    ):
        self.fn = fn
        self.stop_event = threading.Event()
        self._interval = interval
        self._name = name
        self._background_job = None
        self._eb = eb

    def start_backup(self):
        if self._background_job is not None and self._background_job.is_alive():
            return
        self._background_job = spawn_background_thread(
            self._name, self._sync, (), self._eb
        )

    def cancel_backup(self):
        self.stop_event.set()
        if self._background_job is not None:
            self._background_job.join(self._interval)
        # Reset stop event to a new event
        self.stop_event = threading.Event()

    def _sync(self):
        while True:
            try:
                if self.stop_event.wait(self._interval):
                    break
                self.fn()
            except Exception as e:
                self._eb.log_exception("_streaming_fallback_sync", e)


class _StatsigNetwork:
    def __init__(
        self,
        sdk_key: str,
        options: StatsigOptions,
        statsig_metadata: dict,
        error_boundary: _StatsigErrorBoundary,
        diagnostics: Diagnostics,
        shutdown_event,
    ):
        self.sdk_key = sdk_key
        self.error_boundary = error_boundary
        self.statsig_options = options
        self.statsig_metadata = statsig_metadata
        worker: IStatsigNetworkWorker = HttpWorker(
            sdk_key, options, statsig_metadata, error_boundary, diagnostics
        )
        self.dcs_worker: IStatsigNetworkWorker = worker
        self.id_list_worker: IStatsigNetworkWorker = worker
        self.log_event_worker: IStatsigNetworkWorker = worker
        self.http_worker: IStatsigNetworkWorker = worker
        for endpoint, config in options.proxy_configs.items():
            protocol = config.protocol
            if protocol == NetworkProtocol.GRPC:
                worker = GRPCWorker(sdk_key, config)
            elif protocol == NetworkProtocol.GRPC_WEBSOCKET:
                worker = GRPCWebsocketWorker(
                    sdk_key,
                    config,
                    options,
                    error_boundary,
                    diagnostics,
                    shutdown_event,
                )

            if endpoint == NetworkEndpoint.DOWNLOAD_CONFIG_SPECS:
                self.dcs_worker = worker
            elif endpoint == NetworkEndpoint.GET_ID_LISTS:
                self.id_list_worker = worker
            elif endpoint == NetworkEndpoint.LOG_EVENT:
                self.log_event_worker = worker
        self._background_download_configs_from_statsig = None
        self._background_download_id_lists_from_statsig = None

    def is_pull_worker(self, endpoint: str) -> bool:
        if endpoint == NetworkEndpoint.DOWNLOAD_CONFIG_SPECS.value:
            return self.dcs_worker.is_pull_worker()
        if endpoint == NetworkEndpoint.GET_ID_LISTS.value:
            return self.id_list_worker.is_pull_worker()
        if endpoint == NetworkEndpoint.LOG_EVENT.value:
            return self.log_event_worker.is_pull_worker()
        return True

    def get_dcs(
        self,
        on_complete: Any,
        since_time: int = 0,
        log_on_exception: Optional[bool] = False,
        timeout: Optional[int] = None,
    ):
        if self.statsig_options.local_mode:
            logger.warning("Local mode is enabled. Not fetching DCS.")
            return
        self.dcs_worker.get_dcs(on_complete, since_time, log_on_exception, timeout)

    def get_dcs_fallback(
        self,
        on_complete: Any,
        since_time: int = 0,
        log_on_exception: Optional[bool] = False,
        timeout: Optional[int] = None,
    ):
        if self.statsig_options.local_mode:
            logger.warning("Local mode is enabled. Not fetching DCS.")
            return
        dcs_proxy = self.statsig_options.proxy_configs.get(
            NetworkEndpoint.DOWNLOAD_CONFIG_SPECS
        )
        is_proxy_dcs = (
            dcs_proxy
            and dcs_proxy.proxy_address != STATSIG_CDN
            or self.statsig_options.api_for_download_config_specs != STATSIG_CDN
        )
        if is_proxy_dcs:
            self.http_worker.get_dcs_fallback(
                on_complete, since_time, log_on_exception, timeout
            )

    def get_id_lists(
        self,
        on_complete: Any,
        log_on_exception: Optional[bool] = False,
        timeout: Optional[int] = None,
    ):
        if self.statsig_options.local_mode:
            logger.warning("Local mode is enabled. Not fetching ID Lists.")
            return
        self.id_list_worker.get_id_lists(on_complete, log_on_exception, timeout)

    def get_id_lists_fallback(
        self,
        on_complete: Any,
        log_on_exception: Optional[bool] = False,
        timeout: Optional[int] = None,
    ):
        if self.statsig_options.local_mode:
            logger.warning("Local mode is enabled. Not fetching ID Lists.")
            return
        if not self.statsig_options.fallback_to_statsig_api:
            return
        id_list_proxy = self.statsig_options.proxy_configs.get(
            NetworkEndpoint.GET_ID_LISTS
        )
        is_id_lists_proxy = id_list_proxy and id_list_proxy.proxy_address != STATSIG_API
        if is_id_lists_proxy:
            self.http_worker.get_id_lists(on_complete, log_on_exception, timeout)

    def get_id_list(self, on_complete: Any, url, headers, log_on_exception=False):
        if self.statsig_options.local_mode:
            logger.warning("Local mode is enabled. Not fetching ID List.")
            return
        self.http_worker.get_id_list(on_complete, url, headers, log_on_exception)

    def log_events(self, payload, headers=None, log_on_exception=False, retry=0):
        if self.statsig_options.local_mode:
            logger.warning("Local mode is enabled. Not logging events.")
            return None
        return self.log_event_worker.log_events(
            payload, headers=headers, log_on_exception=log_on_exception, retry=retry
        )

    def listen_for_dcs(self, listeners: IStreamingListeners, fallback: Callable):
        if self.statsig_options.local_mode:
            logger.warning("Local mode is enabled. Not listening for DCS.")
            return
        if isinstance(self.dcs_worker, IStatsigWebhookWorker):
            self.dcs_worker.start_listen_for_config_spec(listeners)
            interval = (
                self.statsig_options.rulesets_sync_interval
                or DEFAULT_RULESET_SYNC_INTERVAL
            )
            callbacks = StreamingFallback(
                fn=fallback,
                interval=interval,
                name="dcs_stream_fallback",
                eb=self.error_boundary,
            )
            self.dcs_worker.register_fallback_cb(callbacks)

    def listen_for_id_lists(self, listeners: IStreamingListeners):
        if self.statsig_options.local_mode:
            logger.warning("Local mode is enabled. Not listening for ID Lists.")
            return
        if isinstance(self.id_list_worker, IStatsigWebhookWorker):
            self.id_list_worker.start_listen_for_id_list(listeners)

    def shutdown(self):
        self.dcs_worker.shutdown()
        self.id_list_worker.shutdown()
        self.log_event_worker.shutdown()
