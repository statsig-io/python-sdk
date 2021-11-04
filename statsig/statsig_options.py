from .statsig_environment_tier import StatsigEnvironmentTier
import typing

class StatsigOptions:
    """An object of properties for initializing the sdk with additional parameters"""

    def __init__(self, api: str="https://api.statsig.com/v1/", tier: 'typing.Any'=None):
        self._environment = None
        if tier is not None:
            if isinstance(tier, str) or isinstance(tier, StatsigEnvironmentTier):
                tier_str = tier.value if isinstance(tier, StatsigEnvironmentTier) else tier
                self.set_environment_parameter("tier", tier_str)
            else:
                raise ValueError('StatsigEvent.tier must be a str or StatsigEnvironmentTier')
        if api is None:
            api = "https://api.statsig.com/v1/"
        self.api = api
    
    def set_environment_parameter(self, key: str, value: str):
        if self._environment is None:
            self._environment = {}
        self._environment[key] = value
    
    def _get_evironment(self):
        return self._environment