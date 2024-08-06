import concurrent.futures

from . import globals
from .sdk_configs import _SDK_Configs
from .statsig_network import _StatsigNetwork
from .statsig_options import StatsigOptions
from .batch_event_queue import EventBatchProcessor, BatchEventLogs
from .diagnostics import Diagnostics
from .thread_util import spawn_background_thread, THREAD_JOIN_TIMEOUT

BACKOFF_MULTIPLIER = 2.0

MAX_FAILURE_BACKOFF_INTERVAL_SECONDS = 120.0
MIN_SUCCESS_BACKOFF_INTERVAL_SECONDS = 5.0


class LoggerWorker:
    def __init__(self, net: _StatsigNetwork, error_boundary, options: StatsigOptions, statsig_metadata, shutdown_event,
                 diagnostics: Diagnostics, event_batch_processor: EventBatchProcessor):
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        self._statsig_metadata = statsig_metadata
        self._log_interval = globals.STATSIG_LOGGING_INTERVAL_SECONDS
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
        self.worker_thread = None
        self.spawn_bg_threads_if_needed()

    def spawn_bg_threads_if_needed(self):
        if self._local_mode:
            return
        if self.worker_thread is None or not self.worker_thread.is_alive():
            self.worker_thread = spawn_background_thread(
                "logger_worker_thread",
                self._process_queue,
                (self._shutdown_event,),
                self._error_boundary,
            )

        self.event_batch_processor.spawn_bg_threads_if_needed()

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
        if self.worker_thread is not None:
            self.worker_thread.join(THREAD_JOIN_TIMEOUT)
        self.event_batch_processor.shutdown()
        self._executor.shutdown()

    def _process_queue(self, shutdown_event):
        while True:
            try:
                if shutdown_event.wait(self._log_interval):
                    break
                self.flush_at_interval()
            except Exception as e:
                self._error_boundary.log_exception("_process_queue", e)

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

    def _failure_backoff(self):
        if self._check_override_interval():
            return
        self.backoff_interval = min(self.backoff_interval * BACKOFF_MULTIPLIER,
                                    self.max_failure_backoff_interval)
        self._log_interval = self.backoff_interval
        globals.logger.info(f"Log event failure, backing off for {self._log_interval} seconds")

    def _success_backoff(self):
        if self._check_override_interval():
            return
        if self._log_interval == globals.STATSIG_LOGGING_INTERVAL_SECONDS:
            return
        self.backoff_interval = max(self.backoff_interval / BACKOFF_MULTIPLIER,
                                    self.min_success_backoff_interval)
        self._log_interval = self.backoff_interval
        globals.logger.info(f"Log event success, decreasing backoff to {self._log_interval} seconds")

    def _check_override_interval(self):
        override_interval = _SDK_Configs.get_config_num_value("log_event_interval")
        if override_interval is not None and override_interval > 0:
            self._log_interval = float(override_interval)
            return True
        return False
