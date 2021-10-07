from enum import Enum

class StatsigEnvironment(Enum):
    """
    The environment tier the SDK is running in.
    Used to view data in the Statsig console by tier
    """
    development = "development"
    staging = "staging"
    production = "production"