import threading

from typing import Optional, Union, Set, List

from .statsig_logger_worker import LoggerWorker
from .statsig_network import _StatsigNetwork
from .batch_event_queue import EventBatchProcessor
from .evaluation_details import EvaluationDetails
from .config_evaluation import _ConfigEvaluation
from .statsig_event import StatsigEvent
from .layer import Layer
from . import globals
from .thread_util import spawn_background_thread
from .diagnostics import Diagnostics

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

    event.metadata["reason"] = evaluation_details.reason
    event.metadata["configSyncTime"] = evaluation_details.config_sync_time
    event.metadata["initTime"] = evaluation_details.init_time
    event.metadata["serverTime"] = evaluation_details.server_time


class _StatsigLogger:
    _background_exposure_handler: Optional[threading.Thread]

    def __init__(self, net: _StatsigNetwork, shutdown_event, statsig_metadata, error_boundary, options,
                 diagnostics: Diagnostics):
        self._events: List[StatsigEvent] = []
        self._deduper: Set[str] = set()
        self._net = net
        self._statsig_metadata = statsig_metadata
        self._local_mode = options.local_mode
        self._disabled = options.disable_all_logging
        self._console_logger = globals.logger
        self._logging_interval = globals.STATSIG_BATCHING_INTERVAL_SECONDS
        self._error_boundary = error_boundary
        self._shutdown_event = shutdown_event
        self._background_exposure_handler = None
        self._diagnostics = diagnostics
        event_batch_processor = EventBatchProcessor(options, statsig_metadata, shutdown_event, error_boundary, diagnostics)
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
            user,
            gate,
            value,
            rule_id,
            secondary_exposures,
            evaluation_details: EvaluationDetails,
            is_manual_exposure=False,
    ):
        event = StatsigEvent(user, _GATE_EXPOSURE_EVENT)
        event.metadata = {
            "gate": gate,
            "gateValue": "true" if value else "false",
            "ruleID": rule_id,
        }
        if not self._is_unique_exposure(user, _GATE_EXPOSURE_EVENT, event.metadata):
            return

        if is_manual_exposure:
            event.metadata["isManualExposure"] = "true"

        if secondary_exposures is None:
            secondary_exposures = []
        event._secondary_exposures = secondary_exposures

        _safe_add_evaluation_to_event(evaluation_details, event)
        self.log(event)

    def log_config_exposure(
            self,
            user,
            config,
            rule_id,
            secondary_exposures,
            evaluation_details: EvaluationDetails,
            is_manual_exposure=False,
    ):
        event = StatsigEvent(user, _CONFIG_EXPOSURE_EVENT)
        event.metadata = {
            "config": config,
            "ruleID": rule_id,
        }
        if not self._is_unique_exposure(user, _CONFIG_EXPOSURE_EVENT, event.metadata):
            return
        if is_manual_exposure:
            event.metadata["isManualExposure"] = "true"

        if secondary_exposures is None:
            secondary_exposures = []
        event._secondary_exposures = secondary_exposures

        _safe_add_evaluation_to_event(evaluation_details, event)
        self.log(event)

    def log_layer_exposure(
            self,
            user,
            layer: Layer,
            parameter_name: str,
            config_evaluation: _ConfigEvaluation,
            is_manual_exposure=False,
    ):
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
        if not self._is_unique_exposure(user, _LAYER_EXPOSURE_EVENT, metadata):
            return
        event.metadata = metadata
        if is_manual_exposure:
            event.metadata["isManualExposure"] = "true"

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
