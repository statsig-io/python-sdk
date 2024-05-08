from typing import Optional, Union, Callable, Dict, Any

from .layer import Layer
from .dynamic_config import DynamicConfig
from .feature_gate import FeatureGate
from .statsig_errors import StatsigValueError
from .interface_data_store import IDataStore
from .statsig_environment_tier import StatsigEnvironmentTier
from .output_logger import OutputLogger

DEFAULT_RULESET_SYNC_INTERVAL = 10
DEFAULT_IDLIST_SYNC_INTERVAL = 60
DEFAULT_EVENT_QUEUE_SIZE = 500
DEFAULT_IDLISTS_THREAD_LIMIT = 3
DEFAULT_LOGGING_INTERVAL = 60


class StatsigOptions:
    """An object of properties for initializing the sdk with additional parameters"""

    def __init__(
        self,
        api: Optional[str] = None,
        api_for_download_config_specs: Optional[str] = None,
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
        logging_interval: int = DEFAULT_LOGGING_INTERVAL,
        disable_diagnostics: bool = False,
        custom_logger: Optional[OutputLogger] = None,
        enable_debug_logs = False,
        disable_all_logging = False,
        evaluation_callback: Optional[Callable[[Union[Layer, DynamicConfig, FeatureGate]], None]] = None,
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
            self.event_queue_size = 500
        else:
            self.event_queue_size = event_queue_size
        self.logging_interval = logging_interval
        self.custom_logger = custom_logger
        self.enable_debug_logs = enable_debug_logs
        self.disable_all_logging = disable_all_logging
        self.evaluation_callback = evaluation_callback
        self._set_logging_copy()

    def get_logging_copy(self):
        return self.logging_copy

    def set_environment_parameter(self, key: str, value: str):
        if self._environment is None:
            self._environment = {}
        self._environment[key] = value

    def _get_evironment(self):
        return self._environment

    def _set_logging_copy(self):
        logging_copy: Dict[str, Any] = {}
        if self.api is not None:
            logging_copy["api"] = self.api
        if self._environment != {} and self._environment is not None:
            logging_copy["environment"] = self._environment
        if self.init_timeout:
            logging_copy["init_timeout"] = self.init_timeout
        if self.timeout:
            logging_copy["timeout"] = self.timeout
        if (self.rulesets_sync_interval) != DEFAULT_RULESET_SYNC_INTERVAL:
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
        if self.event_queue_size != DEFAULT_EVENT_QUEUE_SIZE:
            logging_copy["event_queue_size"] = self.event_queue_size
        self.logging_copy = logging_copy
