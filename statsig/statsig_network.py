import importlib
import threading
from typing import Any, Callable, Optional, cast

from . import globals
from .diagnostics import Diagnostics
from .http_worker import HttpWorker, RequestResult
from .interface_network import (
    IStreamingFallback,
    IStreamingListeners,
    NetworkProtocol,
    NetworkEndpoint,
    IStatsigNetworkWorker,
    IStatsigWebhookWorker,
)
from .statsig_context import InitContext
from .statsig_error_boundary import _StatsigErrorBoundary
from .statsig_options import (
    DEFAULT_RULESET_SYNC_INTERVAL,
    AuthenticationMode,
    StatsigOptions,
    STATSIG_CDN,
    ProxyConfig,
)
from .thread_util import spawn_background_thread


class StreamingFallback(IStreamingFallback):
    def __init__(self, fn: Callable, interval: int, name: str, eb: _StatsigErrorBoundary):
        super().__init__()
        self.fn = fn
        self.stop_event = threading.Event()
        self.started = False
        self._interval = interval
        self._name = name
        self._background_job = None
        self._eb = eb

    def backup_started(self):
        return self.started

    def start_backup(self):
        if self._background_job is not None and self._background_job.is_alive():
            return
        self.started = True
        globals.logger.warning(
            f"gRPC streaming falling back to polling for {self._name}. "
            "Please check if the gRPC server is running and ensure the correct server address is configured."
        )
        self._background_job = spawn_background_thread(
            self._name, self._sync, (), self._eb
        )

    def cancel_backup(self):
        self.started = False
        globals.logger.debug("gRPC streaming backup cancelled.")
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
            context: InitContext
    ):
        self.sdk_key = sdk_key
        self.context = context
        self.error_boundary = error_boundary
        self.options = options
        self.diagnostics = diagnostics
        self.shutdown_event = shutdown_event
        self.statsig_metadata = statsig_metadata
        defaultHttpWorker: IStatsigNetworkWorker = HttpWorker(
            sdk_key, options, statsig_metadata, error_boundary, diagnostics, context
        )
        self.dcs_worker: IStatsigNetworkWorker = defaultHttpWorker
        self.id_list_worker: IStatsigNetworkWorker = defaultHttpWorker
        self.log_event_worker: IStatsigNetworkWorker = defaultHttpWorker
        self.http_worker: IStatsigNetworkWorker = defaultHttpWorker
        for endpoint, config in self.options.proxy_configs.items():
            protocol = config.protocol
            if protocol == NetworkProtocol.GRPC:
                self.load_grpc_worker(endpoint, config)
            elif protocol == NetworkProtocol.GRPC_WEBSOCKET:
                self.load_grpc_websocket_worker(endpoint, config)
            elif protocol == NetworkProtocol.HTTP:
                if config.authentication_mode in [AuthenticationMode.TLS, AuthenticationMode.MTLS]:
                    self.load_authenticated_http_worker(endpoint, config)

        self._background_download_configs_from_statsig = None
        self._background_download_id_lists_from_statsig = None
        self._streaming_fallback: Optional[StreamingFallback] = None

    def load_authenticated_http_worker(self, endpoint: NetworkEndpoint, config: ProxyConfig):
        if endpoint == NetworkEndpoint.ALL:
            http_worker = cast(HttpWorker, self.http_worker)
            http_worker.authenticate_request_session(config)
            self.log_event_worker = http_worker
            self.id_list_worker = http_worker
            self.dcs_worker = http_worker
            return

        worker = HttpWorker(self.sdk_key, self.options, self.statsig_metadata, self.error_boundary, self.diagnostics, self.context)
        worker.authenticate_request_session(config)
        if endpoint == NetworkEndpoint.DOWNLOAD_CONFIG_SPECS:
            self.dcs_worker = worker
        elif endpoint == NetworkEndpoint.GET_ID_LISTS:
            self.id_list_worker = worker
        elif endpoint == NetworkEndpoint.LOG_EVENT:
            self.log_event_worker = worker


    def load_grpc_websocket_worker(self, endpoint: NetworkEndpoint, config: ProxyConfig):
        grpc_worker_module = importlib.import_module("statsig.grpc_websocket_worker")
        grpc_webhook_worker_class = getattr(grpc_worker_module, 'GRPCWebsocketWorker')
        grpc_webhook_worker = grpc_webhook_worker_class(
            self.sdk_key,
            config,
            self.options,
            self.error_boundary,
            self.diagnostics,
            self.shutdown_event,
            self.context
        )
        if endpoint == NetworkEndpoint.DOWNLOAD_CONFIG_SPECS:
            self.dcs_worker = grpc_webhook_worker
        elif endpoint == NetworkEndpoint.GET_ID_LISTS:
            self.id_list_worker = grpc_webhook_worker
        elif endpoint == NetworkEndpoint.LOG_EVENT:
            self.log_event_worker = grpc_webhook_worker
        elif endpoint == NetworkEndpoint.ALL:
            self.log_event_worker = grpc_webhook_worker
            self.id_list_worker = grpc_webhook_worker
            self.dcs_worker = grpc_webhook_worker

    def load_grpc_worker(self, endpoint: NetworkEndpoint, config: ProxyConfig):
        grpc_worker_module = importlib.import_module("statsig.grpc_worker")
        grpc_worker_class = getattr(grpc_worker_module, 'GRPCWorker')
        grpc_worker = grpc_worker_class(
            self.sdk_key, config, self.context
        )
        if endpoint == NetworkEndpoint.DOWNLOAD_CONFIG_SPECS:
            self.dcs_worker = grpc_worker
        elif endpoint == NetworkEndpoint.GET_ID_LISTS:
            self.id_list_worker = grpc_worker
        elif endpoint == NetworkEndpoint.LOG_EVENT:
            self.log_event_worker = grpc_worker
        elif endpoint == NetworkEndpoint.ALL:
            self.log_event_worker = grpc_worker
            self.id_list_worker = grpc_worker
            self.dcs_worker = grpc_worker

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
            init_timeout: Optional[int] = None,
    ):
        if self.options.local_mode:
            globals.logger.warning("Local mode is enabled. Not fetching DCS.")
            return
        self.dcs_worker.get_dcs(on_complete, since_time, log_on_exception, init_timeout)

    def get_dcs_fallback(
            self,
            on_complete: Any,
            since_time: int = 0,
            log_on_exception: Optional[bool] = False,
            init_timeout: Optional[int] = None,
    ):
        if self.options.local_mode:
            globals.logger.warning("Local mode is enabled. Not fetching DCS with fallback.")
            return
        dcs_proxy = self.options.proxy_configs.get(NetworkEndpoint.DOWNLOAD_CONFIG_SPECS)
        is_proxy_dcs = (
                dcs_proxy
                and dcs_proxy.proxy_address != STATSIG_CDN
                or self.options.api_for_download_config_specs != STATSIG_CDN
        )
        if is_proxy_dcs:
            self.http_worker.get_dcs_fallback(on_complete, since_time, log_on_exception, init_timeout)

    def get_id_lists(
            self,
            on_complete: Any,
            log_on_exception: Optional[bool] = False,
            init_timeout: Optional[int] = None,
    ):
        if self.options.local_mode:
            globals.logger.warning("Local mode is enabled. Not fetching ID Lists.")
            return
        self.id_list_worker.get_id_lists(on_complete, log_on_exception, init_timeout)

    def get_id_lists_fallback(
            self,
            on_complete: Any,
            log_on_exception: Optional[bool] = False,
            init_timeout: Optional[int] = None,
    ):
        if self.options.local_mode:
            globals.logger.warning("Local mode is enabled. Not fetching ID Lists with fallback.")
            return
        if not self.options.fallback_to_statsig_api:
            return
        id_list_proxy = self.options.proxy_configs.get(
            NetworkEndpoint.GET_ID_LISTS
        )
        id_list_api_override = self.options.api_for_get_id_lists
        is_id_lists_proxy = id_list_api_override != STATSIG_CDN or (
                id_list_proxy and id_list_proxy.proxy_address != STATSIG_CDN)
        if is_id_lists_proxy:
            self.http_worker.get_id_lists_fallback(on_complete, log_on_exception, init_timeout)

    def get_id_list(self, on_complete: Any, url, headers, log_on_exception=False):
        if self.options.local_mode:
            globals.logger.warning("Local mode is enabled. Not fetching ID List.")
            return
        self.http_worker.get_id_list(on_complete, url, headers, log_on_exception)

    def log_events(self, payload, headers=None, log_on_exception=False, retry=0) -> RequestResult:
        if self.options.local_mode:
            globals.logger.warning("Local mode is enabled. Not logging events.")
            return RequestResult(data=None, status_code=None, success=False, error=None)
        return self.log_event_worker.log_events(
            payload, headers=headers, log_on_exception=log_on_exception, retry=retry
        )

    def listen_for_dcs(self, listeners: IStreamingListeners, fallback: Callable):
        if self.options.local_mode:
            globals.logger.warning("Local mode is enabled. Not listening for DCS.")
            return
        if isinstance(self.dcs_worker, IStatsigWebhookWorker) and not self.dcs_worker.config_spec_listening_started():
            self.dcs_worker.start_listen_for_config_spec(listeners)
            interval = (
                    self.options.rulesets_sync_interval
                    or DEFAULT_RULESET_SYNC_INTERVAL
            )
            if self._streaming_fallback is None:
                self._streaming_fallback = StreamingFallback(
                    fn=fallback,
                    interval=interval,
                    name="dcs_stream_fallback",
                    eb=self.error_boundary,
                )
            self.dcs_worker.register_fallback_cb(self._streaming_fallback)

    def listen_for_id_lists(self, listeners: IStreamingListeners):
        if self.options.local_mode:
            globals.logger.warning("Local mode is enabled. Not listening for ID Lists.")
            return
        if isinstance(self.id_list_worker,
                      IStatsigWebhookWorker) and not self.id_list_worker.id_list_listening_started():
            self.id_list_worker.start_listen_for_id_list(listeners)

    def spawn_bg_threads_if_needed(self):
        self.dcs_worker.spawn_bg_threads_if_needed()
        self.id_list_worker.spawn_bg_threads_if_needed()
        self.log_event_worker.spawn_bg_threads_if_needed()

    def shutdown(self):
        self.dcs_worker.shutdown()
        self.id_list_worker.shutdown()
        self.log_event_worker.shutdown()
