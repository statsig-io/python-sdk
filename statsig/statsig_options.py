from enum import Enum
from typing import List, Optional, Union, Callable, Dict, Any

from .utils import JSONValue, to_raw_dict_or_none

from .dynamic_config import DynamicConfig
from .evaluation_details import DataSource
from .feature_gate import FeatureGate
from .interface_data_store import IDataStore
from .interface_network import NetworkProtocol, NetworkEndpoint
from .interface_observability_client import ObservabilityClient
from .layer import Layer
from .output_logger import OutputLogger, LogLevel
from .statsig_environment_tier import StatsigEnvironmentTier
from .statsig_errors import StatsigValueError

DEFAULT_RULESET_SYNC_INTERVAL = 10
DEFAULT_IDLIST_SYNC_INTERVAL = 60
DEFAULT_EVENT_QUEUE_SIZE = 1000
DEFAULT_IDLISTS_THREAD_LIMIT = 3
DEFAULT_LOGGING_INTERVAL = 60
DEFAULT_RETRY_QUEUE_SIZE = 10

STATSIG_API = "https://statsigapi.net/v1/"
STATSIG_CDN = "https://api.statsigcdn.com/v1/"


class AuthenticationMode(str, Enum):
    NONE = "none"
    TLS = "tls"
    MTLS = "mtls"


class ProxyConfig:
    """
    An object of properties for configuring proxy network settings
    Including the network protocol/address, fail over settings, and authentication settings
    """

    def __init__(
            self,
            protocol: NetworkProtocol,
            proxy_address: str,
            # Failover config
            max_retry_attempt: Optional[int] = None,
            retry_backoff_multiplier: Optional[int] = None,
            retry_backoff_base_ms: Optional[int] = None,
            # Push worker failback to polling threshold, fallback immediate set 0,
            # n means fallback after n retry failed
            push_worker_failover_threshold: Optional[int] = None,
            # authentication configuration
            authentication_mode: Optional[AuthenticationMode] = AuthenticationMode.NONE,
            tls_client_cert_path: Optional[str] = None,
            tls_client_key_path: Optional[str] = None,
            tls_ca_cert_path: Optional[str] = None,
    ):
        self.proxy_address = proxy_address
        self.protocol = protocol
        self.max_retry_attempt = max_retry_attempt
        self.retry_backoff_multiplier = retry_backoff_multiplier
        self.retry_backoff_base_ms = retry_backoff_base_ms
        self.push_worker_failover_threshold = push_worker_failover_threshold
        self.authentication_mode = authentication_mode
        self.tls_client_cert_path = tls_client_cert_path
        self.tls_client_key_path = tls_client_key_path
        self.tls_ca_cert_path = tls_ca_cert_path


DEFAULT_PROXY_CONFIG = {
    NetworkEndpoint.ALL: ProxyConfig(
        proxy_address=STATSIG_API, protocol=NetworkProtocol.HTTP
    ),
}


class StatsigOptions:
    """
    An object of properties for initializing the sdk with additional parameters
    All time related options are in seconds
    """

    def __init__(
            self,
            api: Optional[str] = None,
            api_for_download_config_specs: Optional[str] = None,
            api_for_get_id_lists: Optional[str] = None,
            api_for_log_event: Optional[str] = None,
            tier: Union[str, StatsigEnvironmentTier, None] = None,
            init_timeout: Optional[int] = None,
            timeout: Optional[int] = None,
            rulesets_sync_interval: int = DEFAULT_RULESET_SYNC_INTERVAL,
            idlists_sync_interval: int = DEFAULT_IDLIST_SYNC_INTERVAL,
            local_mode: bool = False,
            bootstrap_values: Optional[str] = None,
            rules_updated_callback: Optional[Callable] = None,
            event_queue_size: Optional[int] = DEFAULT_EVENT_QUEUE_SIZE,
            data_store: Optional[IDataStore] = None,
            idlists_thread_limit: int = DEFAULT_IDLISTS_THREAD_LIMIT,
            logging_interval: int = DEFAULT_LOGGING_INTERVAL,  # deprecated
            disable_diagnostics: bool = False,
            custom_logger: Optional[OutputLogger] = None,
            enable_debug_logs=False,  # deprecated
            disable_all_logging=False,
            evaluation_callback: Optional[Callable[[Union[Layer, DynamicConfig, FeatureGate]], None]] = None,
            retry_queue_size: int = DEFAULT_RETRY_QUEUE_SIZE,
            proxy_configs: Optional[Dict[NetworkEndpoint, ProxyConfig]] = None,
            fallback_to_statsig_api: Optional[bool] = False,
            out_of_sync_threshold_in_s: Optional[float] = None,
            # If config is out of sync for {threshold} s, we enforce to fallback logic you defined
            initialize_sources: Optional[List[DataSource]] = None,
            config_sync_sources: Optional[List[DataSource]] = None,
            output_logger_level: Optional[LogLevel] = LogLevel.WARNING,
            overall_init_timeout: Optional[float] = None,
            observability_client: Optional[ObservabilityClient] = None,
            sdk_error_callback: Optional[Callable[[str, Exception], None]] = None,
            events_flushed_callback: Optional[
                Callable[[bool, List[Dict], Optional[int], Optional[Exception]], None]] = None,
            global_custom_fields: Optional[Dict[str, JSONValue]] = None,
            disable_ua_parser: bool = False,
            disable_country_lookup: bool = False,
    ):
        self.data_store = data_store
        self._environment: Union[None, dict] = None
        if tier is not None:
            if isinstance(tier, (str, StatsigEnvironmentTier)):
                tier_str = (
                    tier.value if isinstance(tier, StatsigEnvironmentTier) else tier
                )
                self.set_environment_parameter("tier", tier_str)
            else:
                raise StatsigValueError(
                    "StatsigOptions.tier must be a str or StatsigEnvironmentTier"
                )
        self.api = api
        self.api_for_download_config_specs = api_for_download_config_specs
        self.api_for_get_id_lists = api_for_get_id_lists
        self.api_for_log_event = api_for_log_event
        self.timeout = timeout
        self.init_timeout = init_timeout
        self.rulesets_sync_interval = rulesets_sync_interval
        self.idlists_sync_interval = idlists_sync_interval
        self.idlist_threadpool_size = idlists_thread_limit
        self.local_mode = local_mode
        self.bootstrap_values = bootstrap_values
        self.rules_updated_callback = rules_updated_callback
        self.disable_diagnostics = disable_diagnostics
        if event_queue_size is None:
            self.event_queue_size = DEFAULT_EVENT_QUEUE_SIZE
        else:
            self.event_queue_size = event_queue_size
        self.logging_interval = logging_interval
        self.custom_logger = custom_logger
        self.enable_debug_logs = enable_debug_logs  # deprecated
        self.disable_all_logging = disable_all_logging
        self.evaluation_callback = evaluation_callback
        self.retry_queue_size = retry_queue_size
        self.fallback_to_statsig_api = fallback_to_statsig_api
        self.out_of_sync_threshold_in_s = out_of_sync_threshold_in_s
        if proxy_configs is None:
            self.proxy_configs = DEFAULT_PROXY_CONFIG
        else:
            self.proxy_configs = proxy_configs
        self.initialize_sources = initialize_sources
        self.config_sync_sources = config_sync_sources
        self.output_logger_level = output_logger_level
        self.overall_init_timeout = overall_init_timeout
        self.observability_client = observability_client
        self.sdk_error_callback = sdk_error_callback
        self.events_flushed_callback = events_flushed_callback
        self._logging_copy: Dict[str, Any] = {}
        self.global_custom_fields = global_custom_fields
        self.disable_ua_parser = disable_ua_parser
        self.disable_country_lookup = disable_country_lookup
        self._set_logging_copy()
        self._attributes_changed = False

    def __setattr__(self, name, value):
        if name.startswith("_"):
            super().__setattr__(name, value)
        else:
            if hasattr(self, name) and getattr(self, name) != value:
                self._attributes_changed = True

            super().__setattr__(name, value)

    def get_logging_copy(self):
        if self._logging_copy is None or self._attributes_changed:
            self._set_logging_copy()
        return self._logging_copy

    def set_environment_parameter(self, key: str, value: str):
        if self._environment is None:
            self._environment = {}
        self._environment[key] = value

    def get_sdk_environment_tier(self):
        if self._environment is not None and "tier" in self._environment:
            return self._environment["tier"]
        return "production"

    def _set_logging_copy(self):
        logging_copy: Dict[str, Any] = {}
        if self.api is not None:
            logging_copy["api"] = self.api
        if self.api_for_download_config_specs is not None:
            logging_copy["api_for_download_config_specs"] = (
                self.api_for_download_config_specs
            )
        if self.api_for_get_id_lists is not None:
            logging_copy["api_for_get_id_lists"] = self.api_for_get_id_lists
        if self.api_for_log_event is not None:
            logging_copy["api_for_log_event"] = self.api_for_log_event
        if self._environment != {} and self._environment is not None:
            logging_copy["environment"] = self._environment
        if self.init_timeout:
            logging_copy["init_timeout"] = self.init_timeout
        if self.timeout:
            logging_copy["timeout"] = self.timeout
        if self.rulesets_sync_interval != DEFAULT_RULESET_SYNC_INTERVAL:
            logging_copy["rulesets_sync_interval"] = self.rulesets_sync_interval
        if self.idlists_sync_interval != DEFAULT_IDLIST_SYNC_INTERVAL:
            logging_copy["idlists_sync_interval"] = self.idlists_sync_interval
        if self.idlist_threadpool_size != DEFAULT_IDLISTS_THREAD_LIMIT:
            logging_copy["idlist_threadpool_size"] = self.idlist_threadpool_size
        if self.local_mode:
            logging_copy["local_mode"] = self.local_mode
        if self.bootstrap_values:
            logging_copy["bootstrap_values"] = "SET"
        if self.data_store:
            logging_copy["data_store"] = "SET"
        if self.logging_interval != DEFAULT_LOGGING_INTERVAL:
            logging_copy["logging_interval"] = self.logging_interval
        if self.disable_diagnostics:
            logging_copy["disable_diagnostics"] = self.disable_diagnostics
        if self.disable_all_logging:
            logging_copy["disable_all_logging"] = self.disable_all_logging
        if self.event_queue_size != DEFAULT_EVENT_QUEUE_SIZE:
            logging_copy["event_queue_size"] = self.event_queue_size
        if self.retry_queue_size != DEFAULT_RETRY_QUEUE_SIZE:
            logging_copy["retry_queue_size"] = self.retry_queue_size
        if self.overall_init_timeout is not None:
            logging_copy["overall_init_timeout"] = self.overall_init_timeout
        if self.observability_client is not None:
            logging_copy["observability_client"] = "SET"
        if self.fallback_to_statsig_api:
            logging_copy["fallback_to_statsig_api"] = self.fallback_to_statsig_api
        if self.out_of_sync_threshold_in_s:
            logging_copy["out_of_sync_threshold_in_s"] = self.out_of_sync_threshold_in_s
        if self.initialize_sources:
            logging_copy["initialize_sources"] = "SET"
        if self.config_sync_sources:
            logging_copy["config_sync_sources"] = "SET"
        if self.sdk_error_callback:
            logging_copy["sdk_error_callback"] = "SET"
        if self.global_custom_fields:
            logging_copy["global_custom_fields"] = to_raw_dict_or_none(self.global_custom_fields)
        if self.disable_ua_parser:
            logging_copy["disable_ua_parser"] = self.disable_ua_parser
        if self.disable_country_lookup:
            logging_copy["disable_country_lookup"] = self.disable_country_lookup
        self._logging_copy = logging_copy
        self._attributes_changed = False
