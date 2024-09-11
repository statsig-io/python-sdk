import json
import socket
from typing import Optional, Callable

import grpc

from .utils import get_or_default

from . import globals
from .diagnostics import Marker, Diagnostics
from .grpc.generated.statsig_forward_proxy_pb2 import (ConfigSpecRequest)  # pylint: disable=no-name-in-module
from .grpc.generated.statsig_forward_proxy_pb2_grpc import StatsigForwardProxyStub
from .interface_network import (
    IStreamingFallback,
    NetworkProtocol,
    IStatsigNetworkWorker,
    IStreamingListeners,
    IStatsigWebhookWorker,
)
from .statsig_error_boundary import _StatsigErrorBoundary
from .statsig_errors import StatsigNameError
from .statsig_options import ProxyConfig, StatsigOptions
from .thread_util import spawn_background_thread, THREAD_JOIN_TIMEOUT

KEEP_ALIVE_TIME_MS = 2 * 60 * 60 * 1000  # Ping every 2 hour
DEFAULT_RETRY_LIMIT = 10
DEFAULT_RETRY_BACKOFF_MULTIPLIER = 5
DEFAULT_RETRY_BACKOFF_BASE_MS = 10 * 1000
DEFAULT_RETRY_FALLBACK_THRESHOLD = 4
REQUEST_TIMEOUT = 20


class GRPCWebsocketWorker(IStatsigNetworkWorker, IStatsigWebhookWorker):
    def __init__(
        self,
        sdk_key: str,
        proxy_config: ProxyConfig,
        options: StatsigOptions,
        error_boundary: _StatsigErrorBoundary,
        diagnostics: Diagnostics,
        shutdown_event,
    ):
        self._diagnostics = diagnostics
        self.initialized = False
        self.sdk_key = sdk_key
        self.retry_limit = get_or_default(
            proxy_config.max_retry_attempt, DEFAULT_RETRY_LIMIT
        )
        self.retry_backoff_base_ms = get_or_default(
            proxy_config.retry_backoff_base_ms, DEFAULT_RETRY_BACKOFF_BASE_MS
        )
        self.retry_backoff_multiplier = get_or_default(
            proxy_config.retry_backoff_multiplier, DEFAULT_RETRY_BACKOFF_MULTIPLIER
        )
        self.fallback_threshold = get_or_default(
            proxy_config.push_worker_failover_threshold,
            DEFAULT_RETRY_FALLBACK_THRESHOLD,
        )
        self.options = options
        self.error_boundary = error_boundary
        channel = grpc.insecure_channel(
            proxy_config.proxy_address,
            options=[("grpc.keepalive_time_ms", KEEP_ALIVE_TIME_MS)],
        )
        self.channel = channel
        self.stub = StatsigForwardProxyStub(channel)
        self.dcs_thread = None
        self.dcs_stream = None
        self.listeners: Optional[IStreamingListeners] = None
        self.is_shutting_down = False

        self.remaining_retry = self.retry_limit
        self.retry_backoff = self.retry_backoff_base_ms
        self.lcut = 0
        self.server_host_name = "not set"
        self._timeout = options.timeout or REQUEST_TIMEOUT
        self.retrying = False
        self._shutdown_event = shutdown_event
        self._backup_callbacks: Optional[IStreamingFallback] = None

    @property
    def type(self) -> NetworkProtocol:
        return NetworkProtocol.GRPC_WEBSOCKET

    def is_pull_worker(self) -> bool:
        return False

    def get_dcs(
        self,
        on_complete: Callable,
        since_time: int = 0,
        log_on_exception: Optional[bool] = False,
        timeout: Optional[int] = None,
    ):
        if self.dcs_stream is None:
            self._diagnostics.add_marker(
                Marker().download_config_specs().network_request().start()
            )
            self._start_listening(on_complete, since_time, timeout)

    def get_id_lists(
        self,
        on_complete: Callable,
        log_on_exception: Optional[bool] = False,
        timeout: Optional[int] = None,
    ):
        raise NotImplementedError("Not supported yet")

    def log_events(self, payload, headers=None, log_on_exception=False, retry=0):
        raise NotImplementedError("Not supported yet")

    def _start_listening(self, dcs_data_cb: Callable, since_time=0, timeout=None):
        try:
            request = ConfigSpecRequest(sdkKey=self.sdk_key, sinceTime=since_time)

            if timeout is None:
                timeout = self._timeout
            dcs_data = self.stub.getConfigSpec(request, timeout=timeout)

            self.lcut = dcs_data.lastUpdated
            self._diagnostics.add_marker(
                Marker()
                .download_config_specs()
                .network_request()
                .end(
                    {
                        "networkProtocol": NetworkProtocol.GRPC_WEBSOCKET,
                        "success": True,
                    }
                )
            )
            dcs_data_cb(json.loads(dcs_data.spec), None)
        except Exception as e:
            self.error_boundary.log_exception("grpcWebSocket:initialize", e)
            self._diagnostics.add_marker(
                Marker()
                .download_config_specs()
                .network_request()
                .end(
                    {
                        "success": False,
                        "error": Diagnostics.format_error(e),
                        "networkProtocol": NetworkProtocol.GRPC_WEBSOCKET,
                    }
                )
            )
            dcs_data_cb(None, e)

    def _listen_for_dcs(self, since_time=0):
        try:
            if self.dcs_stream is not None:
                self.get_stream_metadata()
                for response in self.dcs_stream:
                    if self.retrying:
                        self.retrying = False
                        self.on_reconnect()
                    if self.listeners and self.listeners.on_update:
                        if response.lastUpdated > self.lcut:
                            self.lcut = response.lastUpdated
                            self.listeners.on_update(
                                json.loads(response.spec), response.lastUpdated
                            )
        except grpc.RpcError as rpc_error:
            if self.is_shutting_down:
                return
            status_code = rpc_error.code()  # pylint: disable=no-member
            if status_code in (
                grpc.StatusCode.UNAVAILABLE,
                grpc.StatusCode.DEADLINE_EXCEEDED,
            ):
                self.error_boundary.log_exception(
                    "grpcWebSocket: connection error",
                    rpc_error,
                    {
                        "retryAttempt": self.retry_limit - self.remaining_retry,
                        "hostName": socket.gethostname(),
                        "sfpHostName": self.server_host_name,
                    },
                    True,
                )
                if self.listeners and self.listeners.on_error is not None:
                    self.listeners.on_error(rpc_error)
                self._retry_connection(since_time)
            else:
                if self.listeners and self.listeners.on_error is not None:
                    self.listeners.on_error(rpc_error)
        except Exception as e:
            if self.is_shutting_down:
                return
            self.error_boundary.log_exception(
                "grpcWebSocket: unexpected error",
                e,
                {
                    "hostName": socket.gethostname(),
                    "sfpHostName": self.server_host_name,
                },
            )
            if self.listeners and self.listeners.on_error is not None:
                self.listeners.on_error(e)

    def start_listen_for_config_spec(self, listeners: IStreamingListeners) -> None:
        if self.dcs_thread and self.dcs_thread.is_alive():
            return

        def on_update_wrapped(spec, lcut):
            def task():
                listeners.on_update(spec, lcut)

            self.error_boundary.capture(
                "grpcWebSocket:listeners.onUpdate", task, lambda: None
            )

        def on_error_wrapped(error):
            try:
                listeners.on_error(error)
            except Exception:
                pass

        self.listeners = IStreamingListeners(on_update_wrapped, on_error_wrapped)

        request = ConfigSpecRequest(sdkKey=self.sdk_key, sinceTime=self.lcut)

        self.dcs_stream = self.stub.StreamConfigSpec(request)
        if self.dcs_stream is None:
            raise StatsigNameError("Failed to initialize dcs stream")

        self.dcs_thread = spawn_background_thread(
            "dcs_thread", self._listen_for_dcs, (self.lcut,), self.error_boundary
        )

    def start_listen_for_id_list(self, listeners: IStreamingListeners) -> None:
        raise NotImplementedError("Not supported yet")

    def _retry_connection(self, since_time):
        if self.is_shutting_down:
            return
        if self.remaining_retry <= 0:
            self.error_boundary.log_exception(
                "grpcWebSocket: retry exhausted",
                Exception("Exhaust retry attempts, disconnected from server"),
            )
            return
        self.retrying = True
        if self.fallback_threshold == (self.retry_limit - self.remaining_retry):
            if self._backup_callbacks:
                self._backup_callbacks.start_backup()

        if self._shutdown_event.wait(timeout=self.retry_backoff / 1000):
            return
        globals.logger.warning(
            f"Retrying grpc websocket connection... attempt {self.retry_limit - self.remaining_retry + 1}"
        )
        self.remaining_retry -= 1
        self.retry_backoff = self.retry_backoff * self.retry_backoff_multiplier
        since_time_to_use = self.lcut if since_time == 0 else since_time
        request = ConfigSpecRequest(sdkKey=self.sdk_key, sinceTime=since_time_to_use)
        self.dcs_stream = self.stub.StreamConfigSpec(request)
        self._listen_for_dcs(since_time_to_use)

    def on_reconnect(self):
        try:
            raise StatsigNameError("Not a sdk exception - grpcWebSocket: Reconnected")
        except Exception as e:
            self.error_boundary.log_exception(
                "grpcWebSocket: Reconnected",
                e,
                {
                    "retryAttempt": self.retry_limit - self.remaining_retry,
                    "hostName": socket.gethostname(),
                    "sfpHostName": self.server_host_name,
                },
                True,
            )
            self.remaining_retry = self.retry_limit
            self.retry_backoff = self.retry_backoff_base_ms
            if self._backup_callbacks:
                self._backup_callbacks.cancel_backup()

    def get_stream_metadata(self):
        try:
            if self.dcs_stream is not None:
                initial_metadata = self.dcs_stream.initial_metadata()
                for metadata in initial_metadata:
                    if metadata.key == "x-sfp-hostname":
                        self.server_host_name = metadata.value
        except Exception as error:
            self.error_boundary.log_exception(
                "grpcWebSocket: connection error",
                error,
                {
                    "retryAttempt": self.retry_limit - self.remaining_retry,
                    "hostName": socket.gethostname(),
                    "sfpHostName": self.server_host_name,
                },
                True,
            )

    def shutdown(self) -> None:
        self.is_shutting_down = True
        if self._backup_callbacks:
            self._backup_callbacks.cancel_backup()
        if self.dcs_stream:
            self.dcs_stream.cancel()
        if self.dcs_thread:
            self.dcs_thread.join(THREAD_JOIN_TIMEOUT)
        self.channel.close()
