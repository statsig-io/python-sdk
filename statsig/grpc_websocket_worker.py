import json
import os
import socket
import threading
import time
from datetime import datetime, timedelta
from typing import Optional, Callable

import grpc

from . import globals
from .diagnostics import Marker, Diagnostics
from .evaluation_details import DataSource
from .grpc.generated.statsig_forward_proxy_pb2 import (ConfigSpecRequest)  # pylint: disable=no-name-in-module
from .grpc.generated.statsig_forward_proxy_pb2_grpc import StatsigForwardProxyStub
from .interface_network import (
    IStreamingFallback,
    NetworkProtocol,
    IStatsigNetworkWorker,
    IStreamingListeners,
    IStatsigWebhookWorker,
)
from .statsig_context import InitContext
from .statsig_error_boundary import _StatsigErrorBoundary
from .statsig_errors import StatsigNameError
from .statsig_options import ProxyConfig, StatsigOptions, AuthenticationMode
from .thread_util import spawn_background_thread, THREAD_JOIN_TIMEOUT
from .utils import get_or_default

KEEP_ALIVE_TIME_MS = 2 * 60 * 60 * 1000  # Ping every 2 hour
DEFAULT_RETRY_LIMIT = 10
DEFAULT_RETRY_BACKOFF_MULTIPLIER = 5
DEFAULT_RETRY_BACKOFF_BASE_MS = 10 * 1000
DEFAULT_RETRY_FALLBACK_THRESHOLD = 4
REQUEST_TIMEOUT = 20

IDLE_RESTART_TIMEOUT = 2  # 2 hour
CHANNEL_CHECK_INTERVAL = 60 * 5  # 5 minutes
GRPC_CHANNEL_OPTIONS = [("grpc.keepalive_time_ms", KEEP_ALIVE_TIME_MS)]


def load_credential_from_file(filepath, description):
    try:
        real_path = os.path.abspath(filepath)
    except Exception as e:
        globals.logger.error(f"Failed to resolve the absolute path for {description} file at {filepath}: {e}")
        return None

    try:
        with open(real_path, "rb") as f:
            return f.read()
    except Exception as e:
        globals.logger.error(f"Failed to read {description} file at {real_path}: {e}")

    return None


class GRPCWebsocketWorker(IStatsigNetworkWorker, IStatsigWebhookWorker):
    def __init__(
            self,
            sdk_key: str,
            proxy_config: ProxyConfig,
            options: StatsigOptions,
            error_boundary: _StatsigErrorBoundary,
            diagnostics: Diagnostics,
            shutdown_event,
            context: InitContext
    ):
        self.context = context
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
        self.proxy_config = proxy_config
        channel = self.init_channel(proxy_config)
        if channel is not None:
            channel.subscribe(self.channel_state_subscribe)
        self.channel = channel
        self.stub = self.init_stub()
        self.channel_address = proxy_config.proxy_address
        self.dcs_thread = None
        self.dcs_stream = None
        self.listeners: Optional[IStreamingListeners] = None
        self.is_shutting_down = False

        self.remaining_retry = self.retry_limit
        self.retry_backoff = self.retry_backoff_base_ms
        self.lcut = 0
        self.server_host_name = "not set"
        self.timeout = options.timeout or REQUEST_TIMEOUT
        self.retrying = False
        self.started = False
        self.shutdown_event = shutdown_event
        self.backup_callbacks: Optional[IStreamingFallback] = None
        self.last_streamed_time = 0
        self.channel_status = grpc.ChannelConnectivity.IDLE
        self.monitor_thread = None
        self.spawn_bg_threads_if_needed()

    @property
    def type(self) -> NetworkProtocol:
        return NetworkProtocol.GRPC_WEBSOCKET

    def is_pull_worker(self) -> bool:
        return False

    def channel_state_subscribe(self, state):
        globals.logger.log_process("gRPC Streaming", f"Channel state changed to {state}")
        self.channel_status = state

    def is_last_streamed_time_old(self):
        return 0 < self.last_streamed_time < (
                datetime.now() - timedelta(hours=IDLE_RESTART_TIMEOUT)).timestamp()

    def spawn_bg_threads_if_needed(self):
        if self.monitor_thread is None or not self.monitor_thread.is_alive():
            self.monitor_thread = spawn_background_thread("monitor_thread", self.monitor_channel, (),
                                                          self.error_boundary)

    def monitor_channel(self):
        while True:
            try:
                if self.shutdown_event.wait(CHANNEL_CHECK_INTERVAL):
                    break
                self.check_channel_state()
            except Exception as e:
                self.error_boundary.log_exception(
                    "grpcWebSocket: monitor channel",
                    e,
                    {
                        "retryAttempt": self.retry_limit - self.remaining_retry,
                        "hostName": socket.gethostname(),
                        "sfpHostName": self.server_host_name,
                    },
                    log_mode="debug",
                )

    def check_channel_state(self):
        if self.is_last_streamed_time_old() and self.channel_status != grpc.ChannelConnectivity.READY and not self.retrying:
            globals.logger.warning(
                "gRPC Streaming channel has been idle for over 2 hours. Restarting the channel and starting backup.")
            self._restart_dcs_streaming_thread_and_start_backup()

    def init_channel(self, proxy_config: ProxyConfig):
        try:
            if proxy_config.authentication_mode == AuthenticationMode.TLS:
                ca_cert = load_credential_from_file(proxy_config.tls_ca_cert_path, "TLS CA certificate")
                if not ca_cert:
                    return None
                credentials = grpc.ssl_channel_credentials(root_certificates=ca_cert)
                globals.logger.log_process("gRPC Streaming",
                                           "Connecting using an TLS secure channel for gRPC webSocket")
                return grpc.secure_channel(
                    proxy_config.proxy_address, credentials, options=GRPC_CHANNEL_OPTIONS
                )

            if proxy_config.authentication_mode == AuthenticationMode.MTLS:
                client_cert = load_credential_from_file(proxy_config.tls_client_cert_path, "TLS client certificate")
                client_key = load_credential_from_file(proxy_config.tls_client_key_path, "TLS client key")
                ca_cert = load_credential_from_file(proxy_config.tls_ca_cert_path, "TLS CA certificate")
                if not client_cert or not client_key or not ca_cert:
                    return None
                credentials = grpc.ssl_channel_credentials(
                    root_certificates=ca_cert,
                    private_key=client_key,
                    certificate_chain=client_cert,
                )
                globals.logger.log_process("gRPC Streaming",
                                           "Connecting using an mTLS secure channel for gRPC webSocket")
                return grpc.secure_channel(
                    proxy_config.proxy_address, credentials, options=GRPC_CHANNEL_OPTIONS
                )

            globals.logger.log_process("gRPC Streaming", "Connecting using an insecure channel for gRPC webSocket")
            return grpc.insecure_channel(
                proxy_config.proxy_address,
                options=GRPC_CHANNEL_OPTIONS,
            )
        except Exception as e:
            self.error_boundary.log_exception("grpcWebSocket:init_channel", e)
            return None

    def init_stub(self):
        if not self.channel:
            return None
        return StatsigForwardProxyStub(self.channel)

    def get_dcs(
            self,
            on_complete: Callable,
            since_time: int = 0,
            log_on_exception: Optional[bool] = False,
            init_timeout: Optional[int] = None,
    ):
        self.context.source_api = self.proxy_config.proxy_address
        self._diagnostics.add_marker(
            Marker().download_config_specs().network_request().start()
        )
        try:
            request = ConfigSpecRequest(sdkKey=self.sdk_key, sinceTime=since_time)

            if init_timeout is None:
                init_timeout = self.timeout
            dcs_data = self.stub.getConfigSpec(request, timeout=init_timeout)

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
            on_complete(DataSource.NETWORK, json.loads(dcs_data.spec), None)
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
            on_complete(DataSource.NETWORK, None, e)

    def get_id_lists(
            self,
            on_complete: Callable,
            log_on_exception: Optional[bool] = False,
            init_timeout: Optional[int] = None
    ):
        raise NotImplementedError("Get ID Lists is not supported yet for gRPC streaming")

    def log_events(self, payload, headers=None, log_on_exception=False, retry=0):
        raise NotImplementedError("Log events is not supported yet for gRPC streaming")

    def _listen_for_dcs(self, since_time=0):
        try:
            self.started = True
            if self.dcs_stream is not None:
                globals.logger.info("Listening for gRPC stream")
                self.get_stream_metadata()
                for response in self.dcs_stream:
                    self.last_streamed_time = int(time.time())
                    if self.retrying:
                        self.retrying = False
                        self.on_reconnect()
                    if self.listeners and self.listeners.on_update:
                        if response.lastUpdated > self.lcut:
                            self.log_grpc_msg_received(response.lastUpdated)
                            self.lcut = response.lastUpdated
                            self.listeners.on_update(
                                json.loads(response.spec), response.lastUpdated
                            )
        except Exception as e:
            if self.is_shutting_down:
                return
            self.log_grpc_streaming_error("grpcWebSocket:streaming_error", e)
            if self.listeners and self.listeners.on_error is not None:
                self.listeners.on_error(e)
            self._retry_connection(since_time)

    def config_spec_listening_started(self) -> bool:
        return self.dcs_thread is not None and self.dcs_thread.is_alive()

    def start_listen_for_config_spec(self, listeners: IStreamingListeners) -> None:
        if self.config_spec_listening_started():
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

    def id_list_listening_started(self) -> bool:
        raise NotImplementedError("Not supported yet")

    def _restart_dcs_streaming_thread_and_start_backup(self):
        self.retrying = True
        if self.dcs_thread and self.dcs_thread != threading.current_thread():
            globals.logger.log_process("gRPC Streaming", "Restarting the streaming thread")
            self.dcs_thread.join(THREAD_JOIN_TIMEOUT)
        request = ConfigSpecRequest(sdkKey=self.sdk_key, sinceTime=self.lcut)
        self.dcs_stream = self.stub.StreamConfigSpec(request)
        self.dcs_thread = spawn_background_thread(
            "dcs_thread", self._listen_for_dcs, (self.lcut,), self.error_boundary
        )
        if self.backup_callbacks is not None and self.backup_callbacks.backup_started():
            self.backup_callbacks.start_backup()

    def _retry_connection(self, since_time):
        if self.is_shutting_down:
            return
        if self.remaining_retry <= 0:
            globals.logger.error(
                f"Failed to establish a gRPC stream after {self.retry_limit} retries. "
                "Please check if the gRPC server is running and ensure the correct server address is configured."
            )
            self.error_boundary.log_exception(
                "grpcWebSocket: retry exhausted",
                Exception("Exhaust retry attempts, disconnected from server"),
            )
            return
        self.retrying = True
        if self.fallback_threshold == (self.retry_limit - self.remaining_retry):
            if self.backup_callbacks:
                self.backup_callbacks.start_backup()

        if self.shutdown_event.wait(timeout=self.retry_backoff / 1000):
            return
        globals.logger.info(
            f"gRPC stream disconnected. Starting automatic retry attempt {self.retry_limit - self.remaining_retry + 1}"
        )
        self.remaining_retry -= 1
        self.retry_backoff = self.retry_backoff * self.retry_backoff_multiplier
        since_time_to_use = self.lcut if since_time == 0 else since_time
        request = ConfigSpecRequest(sdkKey=self.sdk_key, sinceTime=since_time_to_use)
        self.dcs_stream = self.stub.StreamConfigSpec(request)
        self._listen_for_dcs(since_time_to_use)

    def on_reconnect(self):
        self.log_grpc_reconnect()
        self.remaining_retry = self.retry_limit
        self.retry_backoff = self.retry_backoff_base_ms
        if self.backup_callbacks:
            self.backup_callbacks.cancel_backup()

    def get_stream_metadata(self):
        try:
            if self.dcs_stream is not None:
                initial_metadata = self.dcs_stream.initial_metadata()
                for metadata in initial_metadata:
                    if metadata.key == "x-sfp-hostname":
                        self.server_host_name = metadata.value
        except Exception as error:
            self.error_boundary.log_exception(
                "grpcWebSocket: get stream metadata",
                error,
                {
                    "retryAttempt": self.retry_limit - self.remaining_retry,
                    "hostName": socket.gethostname(),
                    "sfpHostName": self.server_host_name,
                },
                log_mode="debug",
            )

    def shutdown(self) -> None:
        self.is_shutting_down = True
        if self.backup_callbacks:
            self.backup_callbacks.cancel_backup()
        if self.dcs_stream:
            self.dcs_stream.cancel()
        if self.dcs_thread:
            self.dcs_thread.join(THREAD_JOIN_TIMEOUT)
        self.channel.close()

    def log_grpc_msg_received(self, timestamp: int):
        globals.logger.log_process("gRPC Streaming",
                                   f"Received new config spec from gRPC stream at {timestamp}")
        globals.logger.increment("grpc_msg_received", 1, {
            "lcut": timestamp,
        })

    def log_grpc_reconnect(self):
        reconn_str = "Not an sdk exception - grpcWebSocket: Reconnected"
        tags = {
            "retryAttempt": self.retry_limit - self.remaining_retry,
            "hostName": socket.gethostname(),
            "sfpHostName": self.server_host_name,
        }
        globals.logger.info(f"Reconnected to gRPC server at {self.channel_address}")
        globals.logger.increment("grpc_reconnected", 1, tags)
        self.error_boundary.log_exception(
            "grpcWebSocket: Reconnected",
            Exception(reconn_str),
            tags,
            True,
            log_mode="none"
        )

    def log_grpc_streaming_error(self, exception_tag: str, exception: Exception):
        retry_attempt = self.retry_limit - self.remaining_retry
        self.error_boundary.log_exception(
            exception_tag,
            exception,
            {
                "retryAttempt": retry_attempt,
                "hostName": socket.gethostname(),
                "sfpHostName": self.server_host_name,
            },
        )
        globals.logger.distribution("grpc_streaming_failed_with_retry_ct", retry_attempt, {
            "hostName": socket.gethostname(),
            "sfpHostName": self.server_host_name,
        })
