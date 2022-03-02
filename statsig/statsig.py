from .statsig_server import StatsigServer

__instance = StatsigServer()


def initialize(secretKey, options=None):
    __instance.initialize(secretKey, options)


def check_gate(user: object, gate: str):
    return __instance.check_gate(user, gate)


def get_config(user: object, config: str):
    return __instance.get_config(user, config)


def get_experiment(user: object, experiment: str):
    return get_config(user, experiment)


def log_event(event: object):
    __instance.log_event(event)


def override_gate(gate: str, value: bool, user_id: str = None):
    __instance.override_gate(gate, value, user_id)


def override_config(config: str, value: object, user_id: str = None):
    __instance.override_config(config, value, user_id)


def override_experiment(experiment: str, value: object, user_id: str = None):
    __instance.override_experiment(experiment, value, user_id)


def evaluate_all(user: object):
    return __instance.evaluate_all(user)


def shutdown():
    __instance.shutdown()
