import dataclasses
import threading
from typing import Optional
from .layer import Layer
from .statsig_errors import StatsigNameError, StatsigRuntimeError, StatsigValueError
from .statsig_event import StatsigEvent
from .statsig_metadata import _StatsigMetadata

from .statsig_user import StatsigUser
from .spec_store import _SpecStore
from .statsig_error_boundary import _StatsigErrorBoundary
from .evaluator import _Evaluator
from .statsig_network import _StatsigNetwork
from .statsig_logger import _StatsigLogger
from .dynamic_config import DynamicConfig
from .statsig_options import StatsigOptions
from .diagnostics import Diagnostics
from . import globals

RULESETS_SYNC_INTERVAL = 10
IDLISTS_SYNC_INTERVAL = 60


class StatsigServer:
    _initialized: bool

    _errorBoundary: _StatsigErrorBoundary

    _options: Optional[StatsigOptions] = None
    __shutdown_event: Optional[threading.Event] = None
    __statsig_metadata: Optional[dict] = None
    _network: Optional[_StatsigNetwork] = None
    _logger: Optional[_StatsigLogger] = None
    _spec_store: Optional[_SpecStore] = None
    _evaluator: Optional[_Evaluator] = None

    def __init__(self) -> None:
        self._initialized = False

        self._errorBoundary = _StatsigErrorBoundary()

    def initialize(self, sdkKey: str, options: Optional[StatsigOptions] = None):
        if self._initialized:
            globals.logger.info("Statsig is already initialized.")
            return

        if sdkKey is None or not sdkKey.startswith("secret-"):
            raise StatsigValueError(
                'Invalid key provided.  You must use a Server Secret Key from the Statsig console.')

        self._initialize_impl(sdkKey, options)

    def _initialize_impl(self, sdk_key: str, options: StatsigOptions):
        threw_error = False
        try:
            Diagnostics.initialize()
            Diagnostics.mark().overall().start()

            self._errorBoundary.set_api_key(sdk_key)

            if options is None:
                options = StatsigOptions()
            self._options = options
            self.__shutdown_event = threading.Event()
            self.__statsig_metadata = _StatsigMetadata.get()
            self._network = _StatsigNetwork(
                sdk_key,
                self._options,
                self.__statsig_metadata,
                self._errorBoundary)
            self._logger = _StatsigLogger(
                self._network,
                self.__shutdown_event,
                self.__statsig_metadata,
                self._errorBoundary,
                self._options)

            Diagnostics.set_logger(self._logger)
            Diagnostics.set_diagnostics_enabled(self._options.disable_diagnostics)

            self._spec_store = _SpecStore(
                self._network,
                self._options,
                self.__statsig_metadata,
                self._errorBoundary,
                self.__shutdown_event,
            )
            self._evaluator = _Evaluator(self._spec_store)

            self._spec_store.initialize()
            self._initialized = True

        except (StatsigValueError, StatsigNameError, StatsigRuntimeError) as e:
            threw_error = True
            raise e

        except Exception as e:
            threw_error = True
            self._errorBoundary.log_exception("initialize", e)
            self._initialized = True
        finally:
            Diagnostics.mark().overall().end({'success': not threw_error})
            Diagnostics.log_diagnostics('initialize')

    def check_gate(self, user: StatsigUser, gate_name: str, log_exposure=True):
        def task():
            if not self._verify_inputs(user, gate_name):
                return False

            result = self.__check_gate(
                user, gate_name, log_exposure)
            return result.boolean_value

        return self._errorBoundary.capture("check_gate", task, lambda: False)

    def manually_log_gate_exposure(self, user: StatsigUser, gate_name: str):
        user = self.__normalize_user(user)
        result = self._evaluator.check_gate(user, gate_name)
        self._logger.log_gate_exposure(
            user, gate_name, result.boolean_value, result.rule_id, result.secondary_exposures,
            result.evaluation_details, is_manual_exposure=True)

    def get_config(self, user: StatsigUser, config_name: str, log_exposure=True):
        def task():
            if not self._verify_inputs(user, config_name):
                return DynamicConfig({}, config_name, "")

            result = self.__get_config(
                user, config_name, log_exposure)
            return DynamicConfig(
                result.json_value, config_name, result.rule_id, group_name=result.group_name)

        return self._errorBoundary.capture("get_config",
                                           task, lambda: DynamicConfig({}, config_name, ""))

    def manually_log_config_exposure(self, user: StatsigUser, config_name: str):
        user = self.__normalize_user(user)
        result = self._evaluator.get_config(user, config_name)
        self._logger.log_config_exposure(
            user, config_name, result.rule_id, result.secondary_exposures, result.
            evaluation_details, is_manual_exposure=True)

    def get_experiment(self, user: StatsigUser, experiment_name: str, log_exposure=True):
        def task():
            return self.get_config(user, experiment_name, log_exposure)

        return self._errorBoundary.capture("get_experiment",
                                           task, lambda: DynamicConfig({}, experiment_name, ""))

    def manually_log_experiment_exposure(self, user: StatsigUser, experiment_name: str):
        user = self.__normalize_user(user)
        result = self._evaluator.get_config(user, experiment_name)
        self._logger.log_config_exposure(
            user, experiment_name, result.rule_id, result.secondary_exposures, result.evaluation_details,
            is_manual_exposure=True)

    def get_layer(self, user: StatsigUser, layer_name: str, log_exposure=True) -> Layer:
        def task():
            if not self._verify_inputs(user, layer_name):
                return Layer._create(layer_name, {}, "")

            normal_user = self.__normalize_user(user)
            result = self._evaluator.get_layer(normal_user, layer_name)

            def log_func(layer: Layer, parameter_name: str):
                if log_exposure:
                    self._logger.log_layer_exposure(
                        normal_user, layer, parameter_name, result)

            return Layer._create(
                layer_name,
                result.json_value,
                result.rule_id,
                log_func
            )

        return self._errorBoundary.capture("get_layer",
                                           task,
                                           lambda: Layer._create(layer_name, {}, ""))

    def manually_log_layer_parameter_exposure(
            self, user: StatsigUser, layer_name: str, parameter_name: str):
        user = self.__normalize_user(user)
        result = self._evaluator.get_layer(user, layer_name)
        layer = Layer._create(layer_name, result.json_value, result.rule_id)
        self._logger.log_layer_exposure(
            user, layer, parameter_name, result, is_manual_exposure=True)

    def log_event(self, event: StatsigEvent):
        def task():
            if not self._initialized:
                raise StatsigRuntimeError(
                    'Must call initialize before checking gates/configs/experiments or logging events')

            self._verify_bg_threads_running()

            event.user = self.__normalize_user(event.user)
            self._logger.log(event)

        self._errorBoundary.swallow("log_event", task)

    def flush(self):
        if self._logger is not None:
            self._logger.flush()

    def shutdown(self):
        def task():
            self.__shutdown_event.set()
            self._logger.shutdown()
            self._spec_store.shutdown()
            self._initialized = False

        self._errorBoundary.swallow("shutdown", task)

    def override_gate(self, gate: str, value: bool,
                      user_id: Optional[str] = None):
        self._errorBoundary.swallow("override_gate",
                                    lambda: self._evaluator.override_gate(gate, value, user_id))

    def override_config(self, config: str, value: object,
                        user_id: Optional[str] = None):
        self._errorBoundary.swallow("override_config",
                                    lambda: self._evaluator.override_config(config, value, user_id))

    def override_experiment(self, experiment: str,
                            value: object, user_id: Optional[str] = None):
        self._errorBoundary.swallow("override_experiment",
                                    lambda: self._evaluator.override_config(experiment, value, user_id))

    def override_layer(self, layer: str,
                       value: object, user_id: Optional[str] = None):
        self._errorBoundary.swallow("override_layer",
                                    lambda: self._evaluator.override_layer(layer, value, user_id))

    def remove_gate_override(self, gate: str, user_id: Optional[str] = None):
        self._errorBoundary.swallow("remove_gate_override",
                                    lambda: self._evaluator.remove_gate_override(gate, user_id))

    def remove_config_override(self, config: str,
                               user_id: Optional[str] = None):
        self._errorBoundary.swallow("remove_config_override",
                                    lambda: self._evaluator.remove_config_override(config, user_id))

    def remove_experiment_override(
            self, experiment: str, user_id: Optional[str] = None):
        self._errorBoundary.swallow("remove_experiment_override",
                                    lambda: self._evaluator.remove_config_override(experiment, user_id))

    def remove_layer_override(
            self, layer: str, user_id: Optional[str] = None):
        self._errorBoundary.swallow("remove_layer_override",
                                    lambda: self._evaluator.remove_layer_override(layer, user_id))

    def remove_all_overrides(self):
        self._errorBoundary.swallow("remove_all_overrides",
                                    lambda: self._evaluator.remove_all_overrides())

    def get_client_initialize_response(self, user: StatsigUser, client_sdk_key: Optional[str] = None):
        def task():
            return self._evaluator.get_client_initialize_response(
                self.__normalize_user(user), client_sdk_key)

        def recover():
            return None

        return self._errorBoundary.capture("get_client_initialize_response", task, recover)

    def evaluate_all(self, user: StatsigUser):
        def task():
            all_gates = {}
            for gate in self._spec_store.get_all_gates():
                result = self.__check_gate(user, gate, False)
                all_gates[gate] = {
                    "value": result.boolean_value,
                    "rule_id": result.rule_id
                }

            all_configs = {}
            for config in self._spec_store.get_all_configs():
                result = self.__get_config(user, config, False)
                all_configs[config] = {
                    "value": result.json_value,
                    "rule_id": result.rule_id
                }
            return dict({
                "feature_gates": all_gates,
                "dynamic_configs": all_configs
            })

        def recover():
            return dict({
                "feature_gates": {},
                "dynamic_configs": {}
            })

        return self._errorBoundary.capture("evaluate_all", task, recover)

    def _log_diagnostics(self):
        self._logger.log_diagnostics_event("initialize")

    def _verify_inputs(self, user: StatsigUser, variable_name: str):
        if not self._initialized:
            raise StatsigRuntimeError(
                'Must call initialize before checking gates/configs/experiments or logging events')

        if not user or (not user.user_id and not user.custom_ids):
            raise StatsigValueError(
                'A non-empty StatsigUser with user_id or custom_ids is required. See '
                'https://docs.statsig.com/messages/serverRequiredUserID')

        if not variable_name:
            return False

        self._verify_bg_threads_running()

        return True

    def _verify_bg_threads_running(self):
        if self._logger is not None:
            self._logger.spawn_bg_threads_if_needed()

        if self._spec_store is not None:
            self._spec_store.spawn_bg_threads_if_needed()

    def __check_gate(
            self, user: StatsigUser, gate_name: str, log_exposure=True):
        user = self.__normalize_user(user)
        result = self._evaluator.check_gate(user, gate_name)
        if log_exposure:
            self._logger.log_gate_exposure(
                user, gate_name, result.boolean_value, result.rule_id, result.secondary_exposures,
                result.evaluation_details)
        return result

    def __get_config(
            self, user: StatsigUser, config_name: str, log_exposure=True):
        user = self.__normalize_user(user)

        result = self._evaluator.get_config(user, config_name)
        if log_exposure:
            self._logger.log_config_exposure(
                user, config_name, result.rule_id, result.secondary_exposures, result.evaluation_details)
        return result

    def __normalize_user(self, user):
        userCopy = dataclasses.replace(user)
        if self._options is not None and self._options._environment is not None:
            userCopy._statsig_environment = self._options._environment
        return userCopy

    def _sync(self, sync_func, interval):
        while True:
            try:
                if self.__shutdown_event.wait(interval):
                    break
                sync_func()
            except Exception as e:
                self._errorBoundary.log_exception("_sync", e)
