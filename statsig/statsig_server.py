import dataclasses
import json
import logging
import threading
from typing import Optional
from statsig.layer import Layer
from statsig.statsig_errors import StatsigNameError, StatsigRuntimeError, StatsigValueError
from statsig.statsig_event import StatsigEvent
from statsig.statsig_metadata import _StatsigMetadata

from statsig.statsig_user import StatsigUser
from .spec_store import _SpecStore
from .statsig_error_boundary import _StatsigErrorBoundary
from .evaluator import _ConfigEvaluation, _Evaluator
from .statsig_network import _StatsigNetwork
from .statsig_logger import _StatsigLogger
from .dynamic_config import DynamicConfig
from .statsig_options import StatsigOptions

RULESETS_SYNC_INTERVAL = 10
IDLISTS_SYNC_INTERVAL = 60


class StatsigServer:
    _errorBoundary: _StatsigErrorBoundary

    def __init__(self) -> None:
        self._errorBoundary = _StatsigErrorBoundary()

    def initialize(self, sdkKey: str, options=None):
        if sdkKey is None or not sdkKey.startswith("secret-"):
            raise StatsigValueError(
                'Invalid key provided.  You must use a Server Secret Key from the Statsig console.')
        if options is None:
            options = StatsigOptions()
        self._errorBoundary.set_api_key(sdkKey)

        try:
            self._options = options
            self.__shutdown_event = threading.Event()
            self.__statsig_metadata = _StatsigMetadata.get()
            self._network = _StatsigNetwork(sdkKey, options)
            self._logger = _StatsigLogger(
                self._network, self.__shutdown_event, self.__statsig_metadata, self._errorBoundary, options.local_mode,
                options.event_queue_size)
            self._spec_store = _SpecStore(self._network, self._options, self.__statsig_metadata, self._errorBoundary,
                                          self.__shutdown_event)
            self._evaluator = _Evaluator(self._spec_store)

            if not options.local_mode:
                if options.bootstrap_values is not None:
                    self._bootstrap_config_specs()
                else:
                    self._spec_store.download_config_specs()

                self._spec_store.download_id_lists()

            self._initialized = True
        except (StatsigValueError, StatsigNameError, StatsigRuntimeError) as e:
            raise e
        except Exception as e:
            self._errorBoundary.log_exception(e)
            self._initialized = True

    def check_gate(self, user: StatsigUser, gate_name: str):
        def task():
            if not self._verify_inputs(user, gate_name):
                return False

            result = self.__check_gate_server_fallback(user, gate_name)
            return result.boolean_value

        return self._errorBoundary.capture(task, lambda: False)

    def get_config(self, user: StatsigUser, config_name: str):
        def task():
            if not self._verify_inputs(user, config_name):
                return DynamicConfig({}, config_name, "")

            result = self.__get_config_server_fallback(user, config_name)
            return DynamicConfig(result.json_value, config_name, result.rule_id)

        return self._errorBoundary.capture(task, lambda: DynamicConfig({}, config_name, ""))

    def get_experiment(self, user: StatsigUser, experiment_name: str):
        def task():
            return self.get_config(user, experiment_name)

        return self._errorBoundary.capture(task, lambda: DynamicConfig({}, experiment_name, ""))

    def get_layer(self, user: StatsigUser, layer_name: str) -> Layer:
        def task():
            if not self._verify_inputs(user, layer_name):
                return Layer._create(layer_name, {}, "")

            normal_user = self.__normalize_user(user)
            result = self._evaluator.get_layer(normal_user, layer_name)
            result = self.__resolve_eval_result(
                normal_user, layer_name, result=result, log_exposure=True, is_layer=True)

            def log_func(layer: Layer, parameter_name: str):
                self._logger.log_layer_exposure(
                    normal_user, layer, parameter_name, result)

            return Layer._create(
                layer_name,
                result.json_value,
                result.rule_id,
                log_func
            )

        return self._errorBoundary.capture(task, lambda: Layer._create(layer_name, {}, ""))

    def log_event(self, event: StatsigEvent):
        def task():
            if not self._initialized:
                raise StatsigRuntimeError(
                    'Must call initialize before checking gates/configs/experiments or logging events')

            event.user = self.__normalize_user(event.user)
            self._logger.log(event)

        self._errorBoundary.swallow(task)

    def shutdown(self):
        def task():
            self.__shutdown_event.set()
            self._logger.shutdown()
            self._spec_store.shutdown()

        self._errorBoundary.swallow(task)

    def override_gate(self, gate: str, value: bool, user_id: Optional[str] = None):
        self._errorBoundary.swallow(
            lambda: self._evaluator.override_gate(gate, value, user_id))

    def override_config(self, config: str, value: object, user_id: Optional[str] = None):
        self._errorBoundary.swallow(
            lambda: self._evaluator.override_config(config, value, user_id))

    def override_experiment(self, experiment: str, value: object, user_id: Optional[str] = None):
        self._errorBoundary.swallow(
            lambda: self._evaluator.override_config(experiment, value, user_id))

    def get_client_initialize_response(self, user: StatsigUser):
        def task():
            return self._evaluator.get_client_initialize_response(self.__normalize_user(user))

        def recover():
            return None

        return self._errorBoundary.capture(task, recover)

    def evaluate_all(self, user: StatsigUser):
        def task():
            all_gates = dict()
            for gate in self._spec_store.get_all_gates():
                result = self.__check_gate_server_fallback(user, gate, False)
                all_gates[gate] = {
                    "value": result.boolean_value,
                    "rule_id": result.rule_id
                }

            all_configs = dict()
            for config in self._spec_store.get_all_configs():
                result = self.__get_config_server_fallback(user, config, False)
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
                "feature_gates": dict(),
                "dynamic_configs": dict()
            })

        return self._errorBoundary.capture(task, recover)

    def _verify_inputs(self, user: StatsigUser, variable_name: str):
        if not self._initialized:
            raise StatsigRuntimeError(
                'Must call initialize before checking gates/configs/experiments or logging events')
        if not user or (not user.user_id and not user.custom_ids):
            raise StatsigValueError(
                'A non-empty StatsigUser with user_id or custom_ids is required. See https://docs.statsig.com/messages/serverRequiredUserID')
        if not variable_name:
            return False

        return True

    def __check_gate_server_fallback(self, user: StatsigUser, gate_name: str, log_exposure=True):
        user = self.__normalize_user(user)
        result = self._evaluator.check_gate(user, gate_name)
        if result.fetch_from_server:
            network_gate = self._network.post_request("check_gate", {
                "gateName": gate_name,
                "user": user.to_dict(True),
                "statsigMetadata": self.__statsig_metadata,
            })
            if network_gate is None:
                return _ConfigEvaluation()
            return _ConfigEvaluation(boolean_value=network_gate.get("value"), rule_id=network_gate.get("rule_id"))
        elif log_exposure:
            self._logger.log_gate_exposure(
                user, gate_name, result.boolean_value, result.rule_id, result.secondary_exposures)
        return result

    def __get_config_server_fallback(self, user: StatsigUser, config_name: str, log_exposure=True):
        user = self.__normalize_user(user)

        result = self._evaluator.get_config(user, config_name)
        return self.__resolve_eval_result(user, config_name, result, log_exposure, False)

    def __resolve_eval_result(self, user, config_name: str, result: _ConfigEvaluation, log_exposure, is_layer):
        if result.fetch_from_server:
            network_config = self._network.post_request("get_config", {
                "configName": config_name,
                "user": user.to_dict(True),
                "statsigMetadata": self.__statsig_metadata,
            })
            if network_config is None:
                return _ConfigEvaluation()

            return _ConfigEvaluation(json_value=network_config.get("value", {}),
                                     rule_id=network_config.get("ruleID", ""))
        elif log_exposure:
            if not is_layer:
                self._logger.log_config_exposure(
                    user, config_name, result.rule_id, result.secondary_exposures)
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
                self._errorBoundary.log_exception(e)

    def _bootstrap_config_specs(self):
        if self._options.bootstrap_values is None:
            return
        try:
            specs = json.loads(self._options.bootstrap_values)
            if specs is None:
                return

            self._spec_store.process(specs)
        except ValueError:
            # JSON deconding failed, just let background thread update rulesets
            logging.getLogger('statsig.sdk').exception(
                'Failed to parse bootstrap_values')
            return
