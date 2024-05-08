import collections
import concurrent.futures
import threading
from concurrent.futures import Future

from typing import Optional, Union, Deque, Set, List

from .statsig_network import _StatsigNetwork
from .retryable_logs import RetryableLogs
from .evaluation_details import EvaluationDetails
from .config_evaluation import _ConfigEvaluation
from .statsig_event import StatsigEvent
from .layer import Layer
from . import globals
from .thread_util import spawn_background_thread, THREAD_JOIN_TIMEOUT
from .diagnostics import Diagnostics, Context

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
    _background_flush: Optional[threading.Thread]
    _background_retry: Optional[threading.Thread]
    _background_exposure_handler: Optional[threading.Thread]

    def __init__(self, net: _StatsigNetwork, shutdown_event, statsig_metadata, error_boundary, options, diagnostics: Diagnostics):
        self._events: List[StatsigEvent] = []
        self._retry_logs: Deque[RetryableLogs] = collections.deque(maxlen=10)
        self._deduper: Set[str] = set()
        self._net = net
        self._statsig_metadata = statsig_metadata
        self._local_mode = options.local_mode
        self._disabled = options.disable_all_logging
        self._console_logger = globals.logger
        self._logging_interval = options.logging_interval
        self._retry_interval = options.logging_interval
        self._event_queue_size = options.event_queue_size
        self._error_boundary = error_boundary
        self._shutdown_event = shutdown_event
        self._background_flush = None
        self._background_retry = None
        self._background_exposure_handler = None
        self.spawn_bg_threads_if_needed()
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
        self._futures: Deque[Future] = collections.deque(maxlen=10)
        self._diagnostics = diagnostics

    def spawn_bg_threads_if_needed(self):
        if self._local_mode:
            return

        if self._background_flush is None or not self._background_flush.is_alive():
            self._background_flush = spawn_background_thread(
                "logger_background_flush",
                self._periodic_flush,
                (self._shutdown_event,),
                self._error_boundary,
            )

        if self._background_retry is None or not self._background_retry.is_alive():
            self._background_retry = spawn_background_thread(
                "logger_background_retry",
                self._periodic_retry,
                (self._shutdown_event,),
                self._error_boundary,
            )

        if self._background_exposure_handler is None or not self._background_exposure_handler.is_alive():
            self._background_exposure_handler = spawn_background_thread(
                "logger_background_exposure_handler",
                self._periodic_exposure_reset,
                (self._shutdown_event,),
                self._error_boundary,
            )

    def log(self, event):
        if self._local_mode or self._disabled:
            return
        self._events.append(event.to_dict())
        if len(self._events) >= self._event_queue_size:
            self.flush_in_background()

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

    def flush_in_background(self):
        event_count = len(self._events)
        if event_count == 0:
            return
        events_copy = self._events.copy()
        self._events = []

        self._run_on_background_thread(
            lambda: self._flush_to_server(events_copy, event_count)
        )

    def _flush_to_server(self, events_copy, event_count):
        headers = {"STATSIG-EVENT-COUNT": str(event_count)}

        res = self._net.retryable_log_event({
            "events": events_copy,
            "statsigMetadata": self._statsig_metadata,
        }, log_on_exception=True, headers=headers)
        if res is not None:
            self._retry_logs.append(RetryableLogs(res, headers, event_count, 0))

    def flush(self):
        self._add_diagnostics_event(Context.API_CALL)
        self._add_diagnostics_event(Context.LOG_EVENT)
        event_count = len(self._events)
        if event_count == 0:
            return
        events_copy = self._events.copy()
        self._events = []
        self._flush_to_server(events_copy, event_count)

    def shutdown(self):
        self.flush()

        if self._background_flush is not None:
            self._background_flush.join(THREAD_JOIN_TIMEOUT)

        if self._background_retry is not None:
            self._background_retry.join(THREAD_JOIN_TIMEOUT)

        concurrent.futures.wait(self._futures, timeout=THREAD_JOIN_TIMEOUT)
        self._futures.clear()
        self._executor.shutdown()

    def _run_on_background_thread(self, closure):
        if self._shutdown_event.is_set():
            return
        future = self._executor.submit(closure)
        self._futures.append(future)

    def _flush_futures(self):
        for future in concurrent.futures.as_completed(
            self._futures, timeout=THREAD_JOIN_TIMEOUT
        ):
            if future in self._futures:
                self._futures.remove(future)

    def _periodic_flush(self, shutdown_event):
        while True:
            try:
                if shutdown_event.wait(self._logging_interval):
                    break
                self.flush()
                self._flush_futures()
            except Exception as e:
                self._error_boundary.log_exception("_periodic_flush", e)

    def _periodic_exposure_reset(self, shutdown_event):
        while True:
            try:
                if shutdown_event.wait(self._logging_interval):
                    break
                self._deduper = set()
            except Exception as e:
                self._error_boundary.log_exception("_periodic_exposure_reset", e)

    def _periodic_retry(self, shutdown_event):
        while True:
            if shutdown_event.wait(self._retry_interval):
                break
            length = len(self._retry_logs)
            for _i in range(length):
                try:
                    retry_logs = self._retry_logs.pop()
                    retry_logs.retries += 1
                except IndexError:
                    break

                res = self._net.retryable_log_event(
                    retry_logs.payload,
                    log_on_exception=True,
                    retry=retry_logs.retries,
                    headers=retry_logs.headers,
                )
                if res is not None:
                    if retry_logs.retries >= 10:
                        message = (
                            "Failed to post logs after 10 retries, dropping the request"
                        )
                        self._error_boundary.log_exception(
                            "statsig::log_event_failed",
                            Exception(message),
                            {"eventCount": retry_logs.event_count, "error": message},
                            bypass_dedupe = True
                        )
                        self._console_logger.warning(message)
                        return

                    self._retry_logs.append(
                        RetryableLogs(
                            retry_logs.payload,
                            retry_logs.headers,
                            retry_logs.event_count,
                            retry_logs.retries,
                        )
                    )

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

    def _add_diagnostics_event(self, context: Context):
        if self._local_mode or not self._diagnostics.should_log_diagnostics(context):
            return
        markers = self._diagnostics.get_markers(context)
        self._diagnostics.clear_context(context)
        if len(markers) == 0:
            return
        metadata = {
            "markers": [marker.to_dict() for marker in markers],
            "context": context,
        }
        event = StatsigEvent(None, _DIAGNOSTICS_EVENT)
        event.metadata = metadata
        self._events.append(event.to_dict())
