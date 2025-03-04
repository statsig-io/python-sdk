import threading
from typing import Optional, Union, Set, List, Tuple

from . import globals
from .batch_event_queue import EventBatchProcessor
from .config_evaluation import _ConfigEvaluation
from .diagnostics import Diagnostics
from .evaluation_details import EvaluationDetails
from .layer import Layer
from .sdk_configs import _SDK_Configs
from .spec_store import EntityType
from .statsig_event import StatsigEvent
from .statsig_logger_worker import LoggerWorker
from .statsig_network import _StatsigNetwork
from .statsig_user import StatsigUser
from .thread_util import spawn_background_thread
from .ttl_set import TTLSet
from .utils import compute_dedupe_key_for_gate, compute_dedupe_key_for_config, compute_dedupe_key_for_layer, \
    is_hash_in_sampling_rate

_CONFIG_EXPOSURE_EVENT = "statsig::config_exposure"
_LAYER_EXPOSURE_EVENT = "statsig::layer_exposure"
_GATE_EXPOSURE_EVENT = "statsig::gate_exposure"
_DIAGNOSTICS_EVENT = "statsig::diagnostics"

_IGNORED_METADATA_KEYS = {"serverTime", "configSyncTime", "initTime", "reason"}


def _safe_add_evaluation_to_event(
        evaluation_details: Union[EvaluationDetails, None], event: StatsigEvent
):
    if evaluation_details is None or event is None or event.metadata is None:
        return

    event.metadata["reason"] = evaluation_details.detailed_reason()
    event.metadata["configSyncTime"] = evaluation_details.config_sync_time
    event.metadata["initTime"] = evaluation_details.init_time
    event.metadata["serverTime"] = evaluation_details.server_time


class _StatsigLogger:
    _background_exposure_handler: Optional[threading.Thread]

    def __init__(self, net: _StatsigNetwork, shutdown_event, statsig_metadata, error_boundary, options,
                 diagnostics: Diagnostics):
        self._sampling_key_set = TTLSet(shutdown_event)
        self._events: List[StatsigEvent] = []
        self._deduper: Set[str] = set()
        self._net = net
        self._options = options
        self._statsig_metadata = statsig_metadata
        self._local_mode = options.local_mode
        self._disabled = options.disable_all_logging
        self._console_logger = globals.logger
        self._logging_interval = globals.STATSIG_BATCHING_INTERVAL_SECONDS
        self._error_boundary = error_boundary
        self._shutdown_event = shutdown_event
        self._background_exposure_handler = None
        self._diagnostics = diagnostics
        event_batch_processor = EventBatchProcessor(options, statsig_metadata, shutdown_event, error_boundary,
                                                    diagnostics)
        self.event_batch_processor = event_batch_processor
        self._logger_worker = LoggerWorker(net, error_boundary, options, statsig_metadata, shutdown_event, diagnostics,
                                           event_batch_processor)
        self.spawn_bg_threads_if_needed()

    def spawn_bg_threads_if_needed(self):
        if self._local_mode:
            return

        if self._background_exposure_handler is None or not self._background_exposure_handler.is_alive():
            self._background_exposure_handler = spawn_background_thread(
                "logger_background_exposure_handler",
                self._periodic_exposure_reset,
                (self._shutdown_event,),
                self._error_boundary,
            )
        self._logger_worker.spawn_bg_threads_if_needed()

    def log(self, event):
        if self._local_mode or self._disabled:
            return
        self.event_batch_processor.add_event(event.to_dict())

    def log_gate_exposure(
            self,
            user: StatsigUser,
            gate_name: str,
            gate_result: _ConfigEvaluation,
            is_manual_exposure=False,
    ):
        should_log, sampling_rate, shadow_logged = self.__determine_sampling(EntityType.GATE, gate_name, gate_result,
                                                                             user)
        if not should_log:
            return
        event = StatsigEvent(user, _GATE_EXPOSURE_EVENT)
        event.metadata = {
            "gate": gate_name,
            "gateValue": "true" if gate_result.boolean_value else "false",
            "ruleID": gate_result.rule_id,
        }

        if gate_result.version is not None:
            event.metadata["configVersion"] = str(gate_result.version)
        event.statsigMetadata = {}
        if not self._is_unique_exposure(user, _GATE_EXPOSURE_EVENT, event.metadata):
            return

        if is_manual_exposure:
            event.metadata["isManualExposure"] = "true"
        if sampling_rate is not None:
            event.statsigMetadata["samplingRate"] = sampling_rate
        if shadow_logged is not None:
            event.statsigMetadata["shadowLogged"] = shadow_logged
        event.statsigMetadata["samplingMode"] = _SDK_Configs.get_config_str_value("sampling_mode")

        secondary_exposures = gate_result.secondary_exposures or []
        event._secondary_exposures = secondary_exposures

        _safe_add_evaluation_to_event(gate_result.evaluation_details, event)
        self.log(event)

    def log_config_exposure(
            self,
            user: StatsigUser,
            config_name: str,
            config_result: _ConfigEvaluation,
            is_manual_exposure=False,
    ):
        should_log, sampling_rate, shadow_logged = self.__determine_sampling(EntityType.CONFIG, config_name,
                                                                             config_result,
                                                                             user)
        if not should_log:
            return
        event = StatsigEvent(user, _CONFIG_EXPOSURE_EVENT)
        event.metadata = {
            "config": config_name,
            "ruleID": config_result.rule_id,
            "rulePassed": "true" if config_result.boolean_value else "false",
        }
        if config_result.version is not None:
            event.metadata["configVersion"] = str(config_result.version)
        event.statsigMetadata = {}

        if not self._is_unique_exposure(user, _CONFIG_EXPOSURE_EVENT, event.metadata):
            return
        if is_manual_exposure:
            event.metadata["isManualExposure"] = "true"
        if sampling_rate is not None:
            event.statsigMetadata["samplingRate"] = sampling_rate
        if shadow_logged is not None:
            event.statsigMetadata["shadowLogged"] = shadow_logged
        event.statsigMetadata["samplingMode"] = _SDK_Configs.get_config_str_value("sampling_mode")

        secondary_exposures = config_result.secondary_exposures or []
        event._secondary_exposures = secondary_exposures

        _safe_add_evaluation_to_event(config_result.evaluation_details, event)
        self.log(event)

    def log_layer_exposure(
            self,
            user,
            layer: Layer,
            parameter_name: str,
            config_evaluation: _ConfigEvaluation,
            is_manual_exposure=False,
    ):
        should_log, sampling_rate, shadow_logged = self.__determine_sampling(
            EntityType.LAYER, layer.name, config_evaluation, user, parameter_name)
        if not should_log:
            return
        event = StatsigEvent(user, _LAYER_EXPOSURE_EVENT)

        allocated_experiment = ""
        exposures = config_evaluation.undelegated_secondary_exposures
        is_explicit = parameter_name in config_evaluation.explicit_parameters
        if is_explicit:
            exposures = config_evaluation.secondary_exposures
            allocated_experiment = config_evaluation.allocated_experiment

        metadata = {
            "config": layer.name,
            "ruleID": layer.rule_id,
            "allocatedExperiment": allocated_experiment,
            "parameterName": parameter_name,
            "isExplicitParameter": "true" if is_explicit else "false",
        }
        if config_evaluation.version is not None:
            metadata["configVersion"] = str(config_evaluation.version)
        if not self._is_unique_exposure(user, _LAYER_EXPOSURE_EVENT, metadata):
            return
        event.metadata = metadata
        event.statsigMetadata = {}
        if is_manual_exposure:
            event.metadata["isManualExposure"] = "true"
        if sampling_rate is not None:
            event.statsigMetadata["samplingRate"] = sampling_rate
        if shadow_logged is not None:
            event.statsigMetadata["shadowLogged"] = shadow_logged
        event.statsigMetadata["samplingMode"] = _SDK_Configs.get_config_str_value("sampling_mode")

        event._secondary_exposures = [] if exposures is None else exposures

        _safe_add_evaluation_to_event(config_evaluation.evaluation_details, event)

        self.log(event)

    def flush(self):
        self._logger_worker.force_flush()

    def shutdown(self):
        self._logger_worker.shutdown()

    def _periodic_exposure_reset(self, shutdown_event):
        while True:
            try:
                if shutdown_event.wait(self._logging_interval):
                    break
                self._deduper = set()
            except Exception as e:
                self._error_boundary.log_exception("_periodic_exposure_reset", e)

    def log_diagnostics_event(self, metadata):
        event = StatsigEvent(None, _DIAGNOSTICS_EVENT)
        event.metadata = metadata
        self.log(event)

    def _is_unique_exposure(self, user, eventName: str, metadata: Optional[dict]) -> bool:
        if user is None:
            return True
        if len(self._deduper) > 10000:
            self._deduper = set()
        custom_id_key = ""
        if user.custom_ids and isinstance(user.custom_ids, dict):
            custom_id_key = ",".join(user.custom_ids.values())

        metadata_key = ""
        if metadata and isinstance(metadata, dict):
            metadata_key = ",".join(
                str(value)
                for key, value in metadata.items()
                if key not in _IGNORED_METADATA_KEYS
            )

        key = ",".join(
            str(item) for item in [user.user_id, custom_id_key, eventName, metadata_key]
        )

        if key in self._deduper:
            return False

        self._deduper.add(key)
        return True

    def __determine_sampling(self, type: EntityType, name: str, result: _ConfigEvaluation, user: StatsigUser,
                             param_name="") -> Tuple[
        bool, Optional[int], Optional[str]]:  # should_log, logged_sampling_rate, shadow_logged
        try:
            shadow_should_log, logged_sampling_rate = True, None
            env = self._options.get_sdk_environment_tier()
            sampling_mode = _SDK_Configs.get_config_str_value("sampling_mode")
            special_case_sampling_rate = _SDK_Configs.get_config_int_value("special_case_sampling_rate")
            special_case_rules = ["disabled", "default", ""]

            if sampling_mode is None or sampling_mode == "none" or env != "production":
                return True, None, None

            if result.forward_all_exposures:
                return True, None, None

            if result.rule_id.endswith((':override', ':id_override')):
                return True, None, None

            samplingSetKey = f"{name}_{result.rule_id}"
            if not self._sampling_key_set.contains(samplingSetKey):
                self._sampling_key_set.add(samplingSetKey)
                return True, None, None

            if result.seen_analytical_gates:
                return True, None, None

            should_sample = result.sample_rate is not None or result.rule_id in special_case_rules
            if not should_sample:
                return True, None, None

            exposure_key = ""
            if type == EntityType.GATE:
                exposure_key = compute_dedupe_key_for_gate(name, result.rule_id, result.boolean_value,
                                                           user.user_id, user.custom_ids)
            elif type == EntityType.CONFIG:
                exposure_key = compute_dedupe_key_for_config(name, result.rule_id, user.user_id, user.custom_ids)
            elif type == EntityType.LAYER:
                exposure_key = compute_dedupe_key_for_layer(name, result.allocated_experiment, param_name,
                                                            result.rule_id,
                                                            user.user_id, user.custom_ids)

            if result.sample_rate is not None:
                shadow_should_log = is_hash_in_sampling_rate(exposure_key, result.sample_rate)
                logged_sampling_rate = result.sample_rate
            elif result.rule_id in special_case_rules and special_case_sampling_rate is not None:
                shadow_should_log = is_hash_in_sampling_rate(exposure_key, special_case_sampling_rate)
                logged_sampling_rate = special_case_sampling_rate

            shadow_logged = None if logged_sampling_rate is None else "logged" if shadow_should_log else "dropped"
            if sampling_mode == "on":
                return shadow_should_log, logged_sampling_rate, shadow_logged
            if sampling_mode == "shadow":
                return True, logged_sampling_rate, shadow_logged

            return True, None, None
        except Exception as e:
            self._error_boundary.log_exception("__determine_sampling", e, log_mode="debug")
            return True, None, None
