from typing import Optional
from statsig.statsig_event import StatsigEvent
from statsig.statsig_user import StatsigUser
from .statsig_server import StatsigServer

__instance = StatsigServer()


def initialize(secret_key: str, options=None):
    if options.init_timeout is not None:
        __instance.initialize_with_timeout(secret_key, options)
    else:
        __instance.initialize(secret_key, options)


def check_gate(user: StatsigUser, gate: str):
    return __instance.check_gate(user, gate)


def check_gate_with_exposure_logging_disabled(user: StatsigUser, gate: str):
    return __instance.check_gate(user, gate, log_exposure=False)


def manually_log_gate_exposure(user: StatsigUser, gate: str):
    __instance.manually_log_gate_exposure(user, gate)


def get_config(user: StatsigUser, config: str):
    return __instance.get_config(user, config)


def get_config_with_exposure_logging_disabled(user: StatsigUser, config: str):
    return __instance.get_config(user, config, log_exposure=False)


def manually_log_config_exposure(user: StatsigUser, config: str):
    __instance.manually_log_config_exposure(user, config)


def get_experiment(user: StatsigUser, experiment: str):
    return get_config(user, experiment)


def get_experiment_with_exposure_logging_disabled(user: StatsigUser, experiment: str):
    return get_config_with_exposure_logging_disabled(user, experiment)


def manually_log_experiment_exposure(user: StatsigUser, experiment: str):
    __instance.manually_log_experiment_exposure(user, experiment)


def get_layer(user: StatsigUser, layer: str):
    return __instance.get_layer(user, layer)


def get_layer_with_exposure_logging_disabled(user: StatsigUser, layer: str):
    return __instance.get_layer(user, layer, log_exposure=False)


def manually_log_layer_parameter_exposure(user: StatsigUser, layer: str, parameter: str):
    __instance.manually_log_layer_parameter_exposure(user, layer, parameter)


def log_event(event: StatsigEvent):
    __instance.log_event(event)


def override_gate(gate: str, value: bool, user_id: Optional[str] = None):
    __instance.override_gate(gate, value, user_id)


def override_config(config: str, value: object, user_id: Optional[str] = None):
    __instance.override_config(config, value, user_id)


def override_experiment(experiment: str, value: object,
                        user_id: Optional[str] = None):
    __instance.override_experiment(experiment, value, user_id)


def remove_gate_override(gate: str, user_id: Optional[str] = None):
    __instance.remove_gate_override(gate, user_id)


def remove_config_override(config: str, user_id: Optional[str] = None):
    __instance.remove_config_override(config, user_id)


def remove_experiment_override(experiment: str, user_id: Optional[str] = None):
    __instance.remove_experiment_override(experiment, user_id)


def remove_all_overrides():
    __instance.remove_all_overrides()


def get_client_initialize_response(user: StatsigUser):
    return __instance.get_client_initialize_response(user)


def evaluate_all(user: StatsigUser):
    return __instance.evaluate_all(user)


def shutdown():
    __instance.shutdown()


def get_instance():
    return __instance
