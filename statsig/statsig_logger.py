import threading
import queue

from .evaluator import _ConfigEvaluation
from .statsig_event import StatsigEvent
from .layer import Layer

_CONFIG_EXPOSURE_EVENT = "statsig::config_exposure"
_LAYER_EXPOSURE_EVENT = "statsig::layer_exposure"
_GATE_EXPOSURE_EVENT = "statsig::gate_exposure"

class _StatsigLogger:
    def __init__(self, net, shutdown_event, statsig_metadata, error_boundary, local_mode, event_queue_size):
        self._events = list()
        self._retry_logs = queue.Queue(maxsize=10)
        self._net = net
        self._statsig_metadata = statsig_metadata
        self._local_mode = local_mode
        self._event_queue_size = event_queue_size
        self._error_boundary = error_boundary

        self._background_flush = threading.Thread(
            target=self._periodic_flush, args=(shutdown_event,))
        self._background_flush.daemon = True
        self._background_flush.start()

        self._background_retry = threading.Thread(
            target=self._periodic_retry, args=(shutdown_event,))
        self._background_retry.daemon = True
        self._background_retry.start()

    def log(self, event):
        if self._local_mode:
            return
        self._events.append(event.to_dict())
        if len(self._events) >= self._event_queue_size or not self._background_flush.is_alive:
            self._flush()

    def log_gate_exposure(self, user, gate, value, rule_id, secondary_exposures):
        event = StatsigEvent(user, _GATE_EXPOSURE_EVENT)
        event.metadata = {
            "gate": gate,
            "gateValue": "true" if value else "false",
            "ruleID": rule_id,
        }
        if secondary_exposures is None:
            secondary_exposures = []
        event._secondary_exposures = secondary_exposures
        self.log(event)

    def log_config_exposure(self, user, config, rule_id, secondary_exposures):
        event = StatsigEvent(user, _CONFIG_EXPOSURE_EVENT)
        event.metadata = {
            "config": config,
            "ruleID": rule_id,
        }

        if secondary_exposures is None:
            secondary_exposures = []
        event._secondary_exposures = secondary_exposures
        self.log(event)

    def log_layer_exposure(self, user, layer: Layer, parameter_name: str, config_evaluation: _ConfigEvaluation):
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

        event._secondary_exposures = [] if exposures is None else exposures
        self.log(event)

    def _flush(self):
        if len(self._events) == 0:
            return
        events_copy = self._events.copy()
        self._events = list()
        res = self._net.retryable_request("log_event", {
            "events": events_copy,
            "statsigMetadata": self._statsig_metadata,
        })
        if res is not None:
            self._retry_logs.put(res, False)

    def shutdown(self):
        self._flush()
        self._background_flush.join()
        self._background_retry.join()

    def _periodic_flush(self, shutdown_event):
        while True:
            try:
                if shutdown_event.wait(60):
                    break
                self._flush()
            except Exception as e:
                self._error_boundary.log_exception(e)

    def _periodic_retry(self, shutdown_event):
        while True:
            if shutdown_event.wait(60):
                break
            for i in range(self._retry_logs.qsize()):
                payload = self._retry_logs.get()
                res = self._net.retryable_request("log_event", payload)
                if res is not None:
                    self._retry_logs.put(res)
                self._retry_logs.task_done()
