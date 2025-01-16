import functools
import time
from typing import Optional, Dict, Any, Callable

from .initialize_details import InitializeDetails
from .interface_observability_client import ObservabilityClient
from .output_logger import OutputLogger
from .statsig_options import StatsigOptions

TELEMETRY_PREFIX = "statsig.sdk"


class NoopObservabilityClient(ObservabilityClient):
    noop = True

    def init(self, *args, **kwargs):
        pass

    def increment(self, metric_name: str, value: int = 1, tags: Optional[Dict[str, Any]] = None) -> None:
        pass

    def gauge(self, metric_name: str, value: float, tags: Optional[Dict[str, Any]] = None) -> None:
        pass

    def distribution(self, metric_name: str, value: float, tags: Optional[Dict[str, Any]] = None) -> None:
        pass

    def shutdown(self) -> None:
        pass


def handle_exceptions(method):
    @functools.wraps(method)
    def wrapper(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except Exception:
            return None

    return wrapper


class AutoTryCatch:
    def __init_subclass__(cls, **kwargs):
        super(AutoTryCatch, cls).__init_subclass__(**kwargs)
        for attr_name, attr_value in cls.__dict__.items():
            if callable(attr_value) and not attr_name.startswith("__"):
                setattr(cls, attr_name, handle_exceptions(attr_value))


class StatsigTelemetryLogger(AutoTryCatch):
    def __init__(self, logger=None, ob_client: Optional[ObservabilityClient] = None,
                 sdk_error_callback: Optional[Callable[[str, Exception], None]] = None):
        self.high_cardinality_tags = {"lcut", "prev_lcut"}
        self.logger = logger or OutputLogger(TELEMETRY_PREFIX)
        self.ob_client = ob_client or NoopObservabilityClient()
        self.sdk_error_callback = sdk_error_callback

    def set_logger(self, output_logger):
        self.logger = output_logger

    def set_ob_client(self, ob_client):
        self.ob_client = ob_client

    def set_sdk_error_callback(self, sdk_error_callback):
        self.sdk_error_callback = sdk_error_callback

    def init(self):
        self.ob_client.init()

    def set_log_level(self, log_level):
        self.logger.set_log_level(log_level)

    def debug(self, msg, *args, **kwargs):
        self.logger.debug(msg, *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        self.logger.info(msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        self.logger.warning(msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        self.logger.error(msg, *args, **kwargs)

    def exception(self, msg, *args, **kwargs):
        self.logger.exception(msg, *args, **kwargs)

    def log_process(self, process, msg):
        self.logger.log_process(process, msg)

    def increment(self, metric_name: str, value: int = 1, tags: Optional[Dict[str, Any]] = None):
        self.ob_client.increment(f'{TELEMETRY_PREFIX}.{metric_name}', value,
                                 self.filter_high_cardinality_tags(tags or {}))

    def gauge(self, metric_name: str, value: float, tags: Optional[Dict[str, Any]] = None):
        self.ob_client.gauge(f'{TELEMETRY_PREFIX}.{metric_name}', value, self.filter_high_cardinality_tags(tags or {}))

    def distribution(self, metric_name: str, value: float, tags: Optional[Dict[str, Any]] = None):
        self.ob_client.distribution(f'{TELEMETRY_PREFIX}.{metric_name}', value,
                                    self.filter_high_cardinality_tags(tags or {}))

    def log_post_init(self, options: StatsigOptions, init_details: InitializeDetails):
        if options.local_mode:
            if init_details.init_success:
                self.logger.info(
                    "Statsig SDK instance initialized in local mode. No data will be fetched from the Statsig servers.")
            else:
                self.logger.error("Statsig SDK instance failed to initialize in local mode.")
            return

        self.distribution("initialization", init_details.duration,
                          self.filter_high_cardinality_tags({"source": init_details.source,
                                                             "store_populated": init_details.store_populated,
                                                             "init_success": init_details.init_success,
                                                             "init_source_api": init_details.init_source_api}))

        if init_details.init_success:
            if init_details.store_populated:
                self.logger.info(
                    f"Statsig SDK instance initialized successfully with data from {init_details.source}"
                    + (f"[{init_details.init_source_api}]" if init_details.init_source_api else "")
                    + "."
                )
            else:
                self.logger.error(
                    "Statsig SDK instance initialized, but config store is not populated. The SDK is using default values for evaluation.")
        else:
            if init_details.timed_out:
                self.logger.error("Statsig SDK instance initialization timed out.")
            else:
                self.logger.error("Statsig SDK instance Initialized failed!")

    def log_config_sync_update(self, initialized: bool, has_update: bool, lcut: int, prev_lcut: int, source, api):
        if not initialized:
            return  # do not log for initialize
        if not has_update:
            self.log_process("Config Sync", "No update")
            self.increment("config_no_update", 1, {"source": source, "source_api": api})
            return

        lcut_diff = abs(lcut - int(time.time() * 1000))
        if lcut_diff > 0:
            self.distribution("config_propagation_diff", lcut_diff,
                              self.filter_high_cardinality_tags({
                                  "source": source,
                                  "source_api": api,
                                  "lcut": lcut,
                                  "prev_lcut": prev_lcut
                              }))
        self.log_process("Config Sync", f"Received updated configs from {lcut}")

    def log_sdk_exception(self, tag: str, exception: Exception):
        if self.sdk_error_callback is not None:
            self.sdk_error_callback(tag, exception)

        self.increment("sdk_exceptions_count")

    def filter_high_cardinality_tags(self, tags: Dict[str, Any]) -> Dict[str, Any]:
        return {tag: value for tag, value in tags.items()
                if tag not in self.high_cardinality_tags or self.ob_client.should_enable_high_cardinality_for_this_tag(
                tag)}

    def shutdown(self):
        self.ob_client.shutdown()
