from typing import Optional, Union, Callable
from statsig.statsig_errors import StatsigValueError
from .interface_data_store import IDataStore
from .statsig_environment_tier import StatsigEnvironmentTier


class StatsigOptions:
    """An object of properties for initializing the sdk with additional parameters"""

    def __init__(
            self,
            api: str = "https://statsigapi.net/v1/",
            tier: Union[str, StatsigEnvironmentTier, None] = None,
            init_timeout: Optional[int] = None,
            timeout: Optional[int] = None,
            rulesets_sync_interval: int = 10,
            idlists_sync_interval: int = 60,
            local_mode: bool = False,
            bootstrap_values: Optional[str] = None,
            rules_updated_callback: Optional[Callable] = None,
            event_queue_size: Optional[int] = 500,
            data_store: Optional[IDataStore] = None,
            idlists_thread_limit: int = 3,
            logging_interval: int = 60
    ):
        self.data_store = data_store
        self._environment = None
        if tier is not None:
            if isinstance(tier, (str, StatsigEnvironmentTier)):
                tier_str = tier.value if isinstance(
                    tier, StatsigEnvironmentTier) else tier
                self.set_environment_parameter("tier", tier_str)
            else:
                raise StatsigValueError(
                    'StatsigOptions.tier must be a str or StatsigEnvironmentTier')
        if api is None:
            api = "https://statsigapi.net/v1/"
        self.api = api
        self.timeout = timeout
        self.init_timeout = init_timeout
        self.rulesets_sync_interval = rulesets_sync_interval
        self.idlists_sync_interval = idlists_sync_interval
        self.idlist_threadpool_size = idlists_thread_limit
        self.local_mode = local_mode
        self.bootstrap_values = bootstrap_values
        self.rules_updated_callback = rules_updated_callback
        if event_queue_size is None:
            self.event_queue_size = 500
        else:
            self.event_queue_size = event_queue_size
        self.logging_interval = logging_interval

    def set_environment_parameter(self, key: str, value: str):
        if self._environment is None:
            self._environment = {}
        self._environment[key] = value

    def _get_evironment(self):
        return self._environment
