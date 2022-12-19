from typing import Optional
from statsig.statsig_event import StatsigEvent
from statsig.statsig_user import StatsigUser
from .statsig_server import StatsigServer
from .utils import logger

__instance = StatsigServer()


def initialize(secret_key: str, options=None):
    """
    Initializes the global Statsig instance with the given SDK key and options

    :param secret_key: The server SDK key copied from console.statsig.com
    :param options: The StatsigOptions object used to configure the SDK
    """
    logger.log_process("Initialize", "Starting...")
    if options.init_timeout is not None:
        __instance.initialize_with_timeout(secret_key, options)
    else:
        __instance.initialize(secret_key, options)
    if __instance._initialized:
        logger.log_process("Initialize", "Done")
    else:
        logger.log_process("Initialize", "Failed")


def check_gate(user: StatsigUser, gate: str):
    """
    Checks the value of a Feature Gate for the given user

    :param user: The StatsigUser object used for the evaluation
    :param gate: The name of the gate being checked
    :return: True if user passes the gate, False otherwise
    """
    return __instance.check_gate(user, gate)


def check_gate_with_exposure_logging_disabled(user: StatsigUser, gate: str):
    """
    Checks the value of a Feature Gate for the given user without logging an exposure event

    :param user: The StatsigUser object used for the evaluation
    :param gate: The name of the gate being checked
    :return: True if user passes the gate, False otherwise
    """
    return __instance.check_gate(user, gate, log_exposure=False)


def manually_log_gate_exposure(user: StatsigUser, gate: str):
    """
    Logs an exposure event for the gate

    :param user: The StatsigUser object used for the evaluation
    :param gate: The name of the gate being checked
    """
    __instance.manually_log_gate_exposure(user, gate)


def get_config(user: StatsigUser, config: str):
    """
    Gets the DynamicConfig value for the given user

    :param user: The StatsigUser object used for the evaluation
    :param config: The name of the dynamic config
    :return: A DynamicConfig object
    """
    return __instance.get_config(user, config)


def get_config_with_exposure_logging_disabled(user: StatsigUser, config: str):
    """
    Gets the DynamicConfig value for the given user without logging an exposure event

    :param user: The StatsigUser object used for the evaluation
    :param config: The name of the dynamic config
    :return: A DynamicConfig object
    """
    return __instance.get_config(user, config, log_exposure=False)


def manually_log_config_exposure(user: StatsigUser, config: str):
    """
    Logs an exposure event for the dynamic config

    :param user: The StatsigUser object used for the evaluation
    :param config: The name of the dynamic config
    """
    __instance.manually_log_config_exposure(user, config)


def get_experiment(user: StatsigUser, experiment: str):
    """
    Gets the DynamicConfig value of an Experiment for the given user

    :param user: The StatsigUser object used for the evaluation
    :param experiment: The name of the experiment
    :return: A DynamicConfig object
    """
    return get_config(user, experiment)


def get_experiment_with_exposure_logging_disabled(user: StatsigUser, experiment: str):
    """
    Gets the DynamicConfig value of an Experiment for the given user without logging an exposure event

    :param user: The StatsigUser object used for the evaluation
    :param experiment: The name of the experiment
    :return: A DynamicConfig object
    """
    return get_config_with_exposure_logging_disabled(user, experiment)


def manually_log_experiment_exposure(user: StatsigUser, experiment: str):
    """
    Logs an exposure event for the experiment

    :param user: The StatsigUser object used for the evaluation
    :param experiment: The name of the experiment
    """
    __instance.manually_log_experiment_exposure(user, experiment)


def get_layer(user: StatsigUser, layer: str):
    """
    Gets the Layer object for the given user

    :param user: The StatsigUser object used for the evaluation
    :param layer: The name of the layer
    :return: A Layer object
    """
    return __instance.get_layer(user, layer)


def get_layer_with_exposure_logging_disabled(user: StatsigUser, layer: str):
    """
    Gets the Layer object for the given user without logging an exposure event

    :param user: The StatsigUser object used for the evaluation
    :param layer: The name of the layer
    :return: A Layer object
    """
    return __instance.get_layer(user, layer, log_exposure=False)


def manually_log_layer_parameter_exposure(user: StatsigUser, layer: str, parameter: str):
    """
    Logs an exposure event for the parameter in the given layer

    :param user: The StatsigUser object used for the evaluation
    :param layer: The name of the layer
    :param parameter: The name of a parameter in the layer
    """
    __instance.manually_log_layer_parameter_exposure(user, layer, parameter)


def log_event(event: StatsigEvent):
    """
    Logs an event to the Statsig console

    :param event: A StatsigEvent object
    """
    __instance.log_event(event)


def override_gate(gate: str, value: bool, user_id: Optional[str] = None):
    """
    Override the value of a Feature Gate for the given user

    :param gate: The name of the gate being overriden
    :param value: The value to override the gate with
    :param user_id: (Optional) The user_id of the user to override
    """
    __instance.override_gate(gate, value, user_id)


def override_config(config: str, value: object, user_id: Optional[str] = None):
    """
    Override the DynamicConfig value for the given user

    :param config: The name of the dynamic config being overriden
    :param value: The value to override the config with
    :param user_id: (Optional) The user_id of the user to override
    """
    __instance.override_config(config, value, user_id)


def override_experiment(experiment: str, value: object,
                        user_id: Optional[str] = None):
    """
    Override the Experiment value for the given user

    :param experiment: The name of the experiment being overriden
    :param value: The value to override the experiment with
    :param user_id: (Optional) The user_id of the user to override
    """
    __instance.override_experiment(experiment, value, user_id)


def remove_gate_override(gate: str, user_id: Optional[str] = None):
    """
    Remove the overriden value of a Feature Gate for a given user

    :param gate: The name of the gate that was overriden
    :param user_id: (Optional) The user_id of the user to remove override for
    """
    __instance.remove_gate_override(gate, user_id)


def remove_config_override(config: str, user_id: Optional[str] = None):
    """
    Remove the overriden value of a DynamicConfig for a given user

    :param config: The name of the dynamic config that was overriden
    :param user_id: (Optional) The user_id of the user to remove override for
    """
    __instance.remove_config_override(config, user_id)


def remove_experiment_override(experiment: str, user_id: Optional[str] = None):
    """
    Remove the overriden value of an Experiment for a given user

    :param experiment: The name of the experiment that was overriden
    :param user_id: (Optional) The user_id of the user to remove override for
    """
    __instance.remove_experiment_override(experiment, user_id)


def remove_all_overrides():
    """
    Removes all overrides for all users
    """
    __instance.remove_all_overrides()


def get_client_initialize_response(user: StatsigUser):
    """
    Gets all evaluated values for the given user.
    These values can then be given to a Statsig Client SDK via bootstrapping.
    Note: See Python SDK documentation https://docs.statsig.com/server/pythonSDK

    :param user: The StatsigUser object used for evaluation
    :return: An initialize response containing evaluated gates/configs/layers
    """
    return __instance.get_client_initialize_response(user)


def evaluate_all(user: StatsigUser):
    """
    Evaluates all Gates, DynamicConfigs, Experiments

    :param user: The StatsigUser object used for evaluation
    :return: All evaluated gate/configs/experiments
    """
    return __instance.evaluate_all(user)


def shutdown():
    """
    Cleans up Statsig, persisting any Event Logs and cleanup processes
    Using any method is undefined after Shutdown() has been called
    """
    __instance.shutdown()


def get_instance():
    """
    Returns the Statsig instance
    """
    return __instance
