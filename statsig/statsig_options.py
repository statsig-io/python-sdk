from .statsig_environment import StatsigEnvironment

class StatsigOptions:
    def __init__(self):
        self.api = "https://api.statsig.com/v1/"
        self.environment = None

    def set_tier(self, tier):
        if tier is None or (not isinstance(tier, str) and not isinstance(tier, StatsigEnvironment)):
            return
        tier_str = tier.value if isinstance(tier, StatsigEnvironment) else tier
        self.set_environment_parameter("tier", tier_str.lower())
    
    def set_environment_parameter(self, key, value):
        if self.environment is None:
            self.environment = {}
        self.environment[key] = value