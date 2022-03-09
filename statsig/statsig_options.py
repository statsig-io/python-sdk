from .statsig_environment_tier import StatsigEnvironmentTier
import typing


class StatsigOptions:
    """An object of properties for initializing the sdk with additional parameters"""

    def __init__(
        self,
        api: str = "https://api.statsig.com/v1/",
        tier: 'typing.Any' = None,
        timeout: int = None,
        rulesets_sync_interval: int = 10,
        idlists_sync_interval: int = 60,
        local_mode: bool=False,
        bootstrap_values: str = None,
        rules_updated_callback: typing.Callable = None,
    ):
        self._environment = None
        if tier is not None:
            if isinstance(tier, str) or isinstance(tier, StatsigEnvironmentTier):
                tier_str = tier.value if isinstance(
                    tier, StatsigEnvironmentTier) else tier
                self.set_environment_parameter("tier", tier_str)
            else:
                raise ValueError(
                    'StatsigEvent.tier must be a str or StatsigEnvironmentTier')
        if api is None:
            api = "https://api.statsig.com/v1/"
        self.api = api
        self.timeout = timeout
        self.rulesets_sync_interval = rulesets_sync_interval
        self.idlists_sync_interval = idlists_sync_interval
        self.local_mode = local_mode
        self.bootstrap_values = bootstrap_values
        self.rules_updated_callback = rules_updated_callback
    
    def set_environment_parameter(self, key: str, value: str):
        if self._environment is None:
            self._environment = {}
        self._environment[key] = value

    def _get_evironment(self):
        return self._environment
