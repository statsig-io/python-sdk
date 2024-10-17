import threading
from typing import List

from . import globals
from .batch_event_queue import EventBatchProcessor, BatchEventLogs
from .diagnostics import Diagnostics
from .sdk_configs import _SDK_Configs
from .statsig_network import _StatsigNetwork
from .statsig_options import StatsigOptions
from .thread_util import spawn_background_thread, THREAD_JOIN_TIMEOUT

BACKOFF_MULTIPLIER = 2.0

MAX_FAILURE_BACKOFF_INTERVAL_SECONDS = 120.0
MIN_SUCCESS_BACKOFF_INTERVAL_SECONDS = 1.0


class LoggerWorker:
    def __init__(self, net: _StatsigNetwork, error_boundary, options: StatsigOptions, statsig_metadata, shutdown_event,
                 diagnostics: Diagnostics, event_batch_processor: EventBatchProcessor):
        self.max_worker_count = 2
        self._statsig_metadata = statsig_metadata
        self._batching_interval = globals.STATSIG_BATCHING_INTERVAL_SECONDS
        self._log_interval = globals.STATSIG_LOGGING_INTERVAL_SECONDS
        self.lock = threading.Lock()
        self.backoff_interval = globals.STATSIG_LOGGING_INTERVAL_SECONDS
        self.max_failure_backoff_interval = MAX_FAILURE_BACKOFF_INTERVAL_SECONDS
        self.min_success_backoff_interval = min(MIN_SUCCESS_BACKOFF_INTERVAL_SECONDS,
                                                globals.STATSIG_LOGGING_INTERVAL_SECONDS)
        self._local_mode = options.local_mode
        self._error_boundary = error_boundary
        self._diagnostics = diagnostics
        self._shutdown_event = shutdown_event
        self._net = net
        self.event_batch_processor = event_batch_processor
        self.worker_threads: List[threading.Thread] = []
        self._dropped_events_count_logging_thread = None
        self.spawn_bg_threads_if_needed()

    def spawn_bg_threads_if_needed(self):
        if self._local_mode:
            return
        for i in range(self.max_worker_count):
            if len(self.worker_threads) <= i or self.worker_threads[i] is None or not self.worker_threads[i].is_alive():
                worker_thread = spawn_background_thread(
                    f"log_event_worker_thread_{i}",
                    self._process_queue,
                    (self._shutdown_event,),
                    self._error_boundary,
                )
                if len(self.worker_threads) <= i:
                    self.worker_threads.append(worker_thread)
                else:
                    self.worker_threads[i] = worker_thread
        if self._dropped_events_count_logging_thread is None or not self._dropped_events_count_logging_thread.is_alive():
            self._dropped_events_count_logging_thread = spawn_background_thread(
                "logger_worker_batch_queue_and_log_dropped_events_thread",
                self._batch_queue_and_log_dropped_events_count,
                (self._shutdown_event,),
                self._error_boundary,
            )

    def flush_at_interval(self):
        batched_events = self.event_batch_processor.get_batched_event()
        if batched_events is not None:
            self._flush_to_server(batched_events)

    def force_flush(self):
        batched_events = self.event_batch_processor.batch_events(add_to_queue=False)
        if batched_events is not None:
            self._flush_to_server(batched_events)

    def shutdown(self):
        event_batches = self.event_batch_processor.get_all_batched_events()
        for batch in event_batches:
            self._flush_to_server(batch)
        self._send_and_reset_dropped_events_count()
        for worker_thread in self.worker_threads:
            if worker_thread is not None:
                worker_thread.join(THREAD_JOIN_TIMEOUT)
        if self._dropped_events_count_logging_thread is not None:
            self._dropped_events_count_logging_thread.join(THREAD_JOIN_TIMEOUT)
        self.event_batch_processor.shutdown()

    def _process_queue(self, shutdown_event):
        while True:
            try:
                if shutdown_event.wait(self._get_curr_interval()):
                    break
                self.flush_at_interval()
            except Exception as e:
                self._error_boundary.log_exception("_process_queue", e)

    def _batch_queue_and_log_dropped_events_count(self, shutdown_event):
        while True:
            try:
                if shutdown_event.wait(self._batching_interval):
                    break
                self.event_batch_processor.batch_events()
                self._send_and_reset_dropped_events_count()
            except Exception as e:
                self._error_boundary.log_exception("_batch_queue_and_send_dropped_events_count", e)

    def _send_and_reset_dropped_events_count(self):
        count = self.event_batch_processor.get_dropped_event_count()
        if count > 0:
            message = (
                f"Dropped {count} events due to events input higher than event flushing qps"
            )
            self._error_boundary.log_exception(
                "statsig::log_event_dropped_event_count",
                Exception(message),
                {"eventCount": count, "loggingInterval": self._log_interval, "error": message},
                bypass_dedupe=True
            )
            self._dropped_events_count = 0

    def _flush_to_server(self, batched_events: BatchEventLogs):
        if self._local_mode:
            return
        res = self._net.log_events(batched_events.payload, retry=batched_events.retries,
                                   log_on_exception=True, headers=batched_events.headers)
        if res is not None:
            if batched_events.retries >= 10:
                message = (
                    f"Failed to post {batched_events.event_count} logs after 10 retries, dropping the request"
                )
                self._error_boundary.log_exception(
                    "statsig::log_event_failed",
                    Exception(message),
                    {"eventCount": batched_events.event_count, "error": message},
                    bypass_dedupe=True
                )
                globals.logger.warning(message)
                return

            self._failure_backoff()

            self.event_batch_processor.add_to_batched_events_queue(
                BatchEventLogs(
                    batched_events.payload,
                    batched_events.headers,
                    batched_events.event_count,
                    batched_events.retries + 1,
                )
            )
        else:
            self._success_backoff()

    def _get_curr_interval(self):
        with self.lock:
            return self._log_interval

    def _failure_backoff(self):
        if self._check_override_interval():
            return
        with self.lock:
            self.backoff_interval = min(self.backoff_interval * BACKOFF_MULTIPLIER,
                                        self.max_failure_backoff_interval)
            self._log_interval = self.backoff_interval
            globals.logger.info(f"Log event failure, backing off for {self._log_interval} seconds")

    def _success_backoff(self):
        if self._check_override_interval():
            return
        with self.lock:
            if self._log_interval == globals.STATSIG_LOGGING_INTERVAL_SECONDS:
                return
            self.backoff_interval = max(self.backoff_interval / BACKOFF_MULTIPLIER,
                                        self.min_success_backoff_interval)
            self._log_interval = self.backoff_interval
            globals.logger.info(f"Log event success, decreasing backoff to {self._log_interval} seconds")

    def _check_override_interval(self):
        with self.lock:
            override_interval = _SDK_Configs.get_config_num_value("event_logging_interval_seconds")
            if override_interval is not None and override_interval > 0:
                self._log_interval = float(override_interval)
                return True
            return False
