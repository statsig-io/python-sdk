from typing import Optional
from statsig.statsig_event import StatsigEvent
from statsig.statsig_user import StatsigUser
from .statsig_server import StatsigServer

__instance = StatsigServer()


def initialize(secret_key: str, options=None):
    __instance.initialize(secret_key, options)


def check_gate(user: StatsigUser, gate: str):
    return __instance.check_gate(user, gate)


def get_config(user: StatsigUser, config: str):
    return __instance.get_config(user, config)


def get_experiment(user: StatsigUser, experiment: str):
    return get_config(user, experiment)


def get_layer(user: StatsigUser, layer: str):
    return __instance.get_layer(user, layer)


def log_event(event: StatsigEvent):
    __instance.log_event(event)


def override_gate(gate: str, value: bool, user_id: Optional[str] = None):
    __instance.override_gate(gate, value, user_id)


def override_config(config: str, value: object, user_id: Optional[str] = None):
    __instance.override_config(config, value, user_id)


def override_experiment(experiment: str, value: object, user_id: Optional[str] = None):
    __instance.override_experiment(experiment, value, user_id)


def get_client_initialize_response(user: StatsigUser):
    return __instance.get_client_initialize_response(user)


def evaluate_all(user: StatsigUser):
    return __instance.evaluate_all(user)


def shutdown():
    __instance.shutdown()


def get_instance():
    return __instance
