from typing import Optional
from statsig.statsig_event import StatsigEvent
from statsig.statsig_user import StatsigUser
from .statsig_server import StatsigServer

__instance = StatsigServer()


# Initializes the global Statsig instance with the given SDK key and options
def initialize(secret_key: str, options=None):
    if options.init_timeout is not None:
        __instance.initialize_with_timeout(secret_key, options)
    else:
        __instance.initialize(secret_key, options)


# Checks the value of a Feature Gate for the given user
def check_gate(user: StatsigUser, gate: str):
    return __instance.check_gate(user, gate)


# Checks the value of a Feature Gate for the given user without logging an exposure event
def check_gate_with_exposure_logging_disabled(user: StatsigUser, gate: str):
    return __instance.check_gate(user, gate, log_exposure=False)


# Logs an exposure event for the gate
def manually_log_gate_exposure(user: StatsigUser, gate: str):
    __instance.manually_log_gate_exposure(user, gate)


# Gets the DynamicConfig value for the given user
def get_config(user: StatsigUser, config: str):
    return __instance.get_config(user, config)


# Gets the DynamicConfig value for the given user without logging an exposure event
def get_config_with_exposure_logging_disabled(user: StatsigUser, config: str):
    return __instance.get_config(user, config, log_exposure=False)


# Logs an exposure event for the dynamic config
def manually_log_config_exposure(user: StatsigUser, config: str):
    __instance.manually_log_config_exposure(user, config)


# Gets the DynamicConfig value of an Experiment for the given user
def get_experiment(user: StatsigUser, experiment: str):
    return get_config(user, experiment)


# Gets the DynamicConfig value of an Experiment for the given user without logging an exposure event
def get_experiment_with_exposure_logging_disabled(user: StatsigUser, experiment: str):
    return get_config_with_exposure_logging_disabled(user, experiment)


# Logs an exposure event for the experiment
def manually_log_experiment_exposure(user: StatsigUser, experiment: str):
    __instance.manually_log_experiment_exposure(user, experiment)


# Gets the Layer object for the given user
def get_layer(user: StatsigUser, layer: str):
    return __instance.get_layer(user, layer)


# Gets the Layer object for the given user without logging an exposure event
def get_layer_with_exposure_logging_disabled(user: StatsigUser, layer: str):
    return __instance.get_layer(user, layer, log_exposure=False)


# Logs an exposure event for the parameter in the given layer
def manually_log_layer_parameter_exposure(user: StatsigUser, layer: str, parameter: str):
    __instance.manually_log_layer_parameter_exposure(user, layer, parameter)


# Logs an event to the Statsig console
def log_event(event: StatsigEvent):
    __instance.log_event(event)


# Override the value of a Feature Gate for the given user
def override_gate(gate: str, value: bool, user_id: Optional[str] = None):
    __instance.override_gate(gate, value, user_id)


# Override the DynamicConfig value for the given user
def override_config(config: str, value: object, user_id: Optional[str] = None):
    __instance.override_config(config, value, user_id)


# Override the Experiment value for the given user
def override_experiment(experiment: str, value: object,
                        user_id: Optional[str] = None):
    __instance.override_experiment(experiment, value, user_id)


# Remove the overriden value of a Feature Gate for a given user
def remove_gate_override(gate: str, user_id: Optional[str] = None):
    __instance.remove_gate_override(gate, user_id)


# Remove the overriden value of a DynamicConfig for a given user
def remove_config_override(config: str, user_id: Optional[str] = None):
    __instance.remove_config_override(config, user_id)


# Remove the overriden value of an Experiment for a given user
def remove_experiment_override(experiment: str, user_id: Optional[str] = None):
    __instance.remove_experiment_override(experiment, user_id)


# Removes all overrides for all users
def remove_all_overrides():
    __instance.remove_all_overrides()


# Returns an object representing the data stored within the initialized Statsig instance.
# Formatted such that it can be used to bootstrap an SDK.
def get_client_initialize_response(user: StatsigUser):
    return __instance.get_client_initialize_response(user)


# Evaluates all Gates, DynamicConfigs, Experiments
def evaluate_all(user: StatsigUser):
    return __instance.evaluate_all(user)


# Cleans up Statsig, persisting any Event Logs and cleanup processes
# Using any method is undefined after Shutdown() has been called
def shutdown():
    __instance.shutdown()


# Returns the Statsig instance
def get_instance():
    return __instance
