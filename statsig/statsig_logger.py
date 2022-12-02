import collections
import threading
from typing import Optional

from .evaluation_details import EvaluationDetails
from .evaluator import _ConfigEvaluation
from .statsig_event import StatsigEvent
from .layer import Layer
from .thread_util import spawn_background_thread, THREAD_JOIN_TIMEOUT

_CONFIG_EXPOSURE_EVENT = "statsig::config_exposure"
_LAYER_EXPOSURE_EVENT = "statsig::layer_exposure"
_GATE_EXPOSURE_EVENT = "statsig::gate_exposure"


def _safe_add_evaluation_to_event(
        evaluation_details: EvaluationDetails, event: StatsigEvent):
    if evaluation_details is None:
        return

    event.metadata["reason"] = evaluation_details.reason
    event.metadata["configSyncTime"] = evaluation_details.config_sync_time
    event.metadata["initTime"] = evaluation_details.init_time
    event.metadata["serverTime"] = evaluation_details.server_time


class _StatsigLogger:
    _background_flush: Optional[threading.Thread]
    _background_retry: Optional[threading.Thread]

    def __init__(self, net, shutdown_event, statsig_metadata, error_boundary, options):
        self._events = []
        self._retry_logs = collections.deque(maxlen=10)
        self._net = net
        self._statsig_metadata = statsig_metadata
        self._local_mode = options.local_mode
        self._logging_interval = options.logging_interval
        self._retry_interval = options.logging_interval
        self._event_queue_size = options.event_queue_size
        self._error_boundary = error_boundary
        self._shutdown_event = shutdown_event
        self._background_flush = None
        self._background_retry = None
        self.spawn_bg_threads_if_needed()

    def spawn_bg_threads_if_needed(self):
        if self._local_mode:
            return

        if self._background_flush is None or not self._background_flush.is_alive():
            self._background_flush = spawn_background_thread(
                self._periodic_flush, (self._shutdown_event,), self._error_boundary)

        if self._background_retry is None or not self._background_retry.is_alive():
            self._background_retry = spawn_background_thread(
                self._periodic_retry, (self._shutdown_event,), self._error_boundary)

    def log(self, event):
        if self._local_mode:
            return
        self._events.append(event.to_dict())
        if len(self._events) >= self._event_queue_size:
            self._flush()

    def log_gate_exposure(self, user, gate, value, rule_id, secondary_exposures,
                          evaluation_details: EvaluationDetails, is_manual_exposure=False):
        event = StatsigEvent(user, _GATE_EXPOSURE_EVENT)
        event.metadata = {
            "gate": gate,
            "gateValue": "true" if value else "false",
            "ruleID": rule_id,
        }
        if is_manual_exposure:
            event.metadata["isManualExposure"] = "true"

        if secondary_exposures is None:
            secondary_exposures = []
        event._secondary_exposures = secondary_exposures

        _safe_add_evaluation_to_event(evaluation_details, event)
        self.log(event)

    def log_config_exposure(self, user, config, rule_id, secondary_exposures,
                            evaluation_details: EvaluationDetails, is_manual_exposure=False):
        event = StatsigEvent(user, _CONFIG_EXPOSURE_EVENT)
        event.metadata = {
            "config": config,
            "ruleID": rule_id,
        }
        if is_manual_exposure:
            event.metadata["isManualExposure"] = "true"

        if secondary_exposures is None:
            secondary_exposures = []
        event._secondary_exposures = secondary_exposures

        _safe_add_evaluation_to_event(evaluation_details, event)
        self.log(event)

    def log_layer_exposure(self, user, layer: Layer, parameter_name: str,
                           config_evaluation: _ConfigEvaluation, is_manual_exposure=False):
        event = StatsigEvent(user, _LAYER_EXPOSURE_EVENT)

        allocated_experiment = ""
        exposures = config_evaluation.undelegated_secondary_exposures
        is_explicit = parameter_name in config_evaluation.explicit_parameters
        if is_explicit:
            exposures = config_evaluation.secondary_exposures
            allocated_experiment = config_evaluation.allocated_experiment

        event.metadata = {
            "config": layer.name,
            "ruleID": layer.rule_id,
            "allocatedExperiment": allocated_experiment,
            "parameterName": parameter_name,
            "isExplicitParameter": "true" if is_explicit else "false"
        }
        if is_manual_exposure:
            event.metadata["isManualExposure"] = "true"

        event._secondary_exposures = [] if exposures is None else exposures

        _safe_add_evaluation_to_event(
            config_evaluation.evaluation_details, event)
        self.log(event)

    def _flush(self):
        if len(self._events) == 0:
            return
        events_copy = self._events.copy()
        self._events = []
        res = self._net.retryable_request("log_event", {
            "events": events_copy,
            "statsigMetadata": self._statsig_metadata,
        })
        if res is not None:
            self._retry_logs.append(res)

    def shutdown(self):
        self._flush()
        self._background_flush.join(THREAD_JOIN_TIMEOUT)
        self._background_retry.join(THREAD_JOIN_TIMEOUT)

    def _periodic_flush(self, shutdown_event):
        while True:
            try:
                if shutdown_event.wait(self._logging_interval):
                    break
                self._flush()
            except Exception as e:
                self._error_boundary.log_exception(e)

    def _periodic_retry(self, shutdown_event):
        while True:
            if shutdown_event.wait(self._retry_interval):
                break

            length = len(self._retry_logs)
            for _i in range(length):
                try:
                    payload = self._retry_logs.pop()
                except IndexError:
                    break

                res = self._net.retryable_request("log_event", payload)
                if res is not None:
                    self._retry_logs.append(res)
