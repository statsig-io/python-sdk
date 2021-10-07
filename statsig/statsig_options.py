from dataclasses import dataclass
from .statsig_environment import StatsigEnvironment

@dataclass
class StatsigOptions:
    """An object of properties for initializing the sdk with advanced options"""
    api: str = "https://api.statsig.com/v1/"
    environment: dict = None

    def set_tier(self, tier):
        if tier is None or (not isinstance(tier, str) and not isinstance(tier, StatsigEnvironment)):
            return
        tier_str = tier.value if isinstance(tier, StatsigEnvironment) else tier
        self.set_environment_parameter("tier", tier_str.lower())
    
    def set_environment_parameter(self, key, value):
        if self.environment is None:
            self.environment = {}
        self.environment[key] = value