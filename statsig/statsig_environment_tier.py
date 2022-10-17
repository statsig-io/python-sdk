from enum import Enum


class StatsigEnvironmentTier(str, Enum):
    """
    The environment tier the SDK is running in.
    Used to view data in the Statsig console by tier
    """
    development = "development"
    staging = "staging"
    production = "production"
