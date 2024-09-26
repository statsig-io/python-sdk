import threading
from collections import deque
from dataclasses import dataclass
from typing import Dict, List, Deque

from . import globals
from .diagnostics import Context
from .sdk_configs import _SDK_Configs
from .statsig_event import StatsigEvent
from .statsig_options import StatsigOptions, DEFAULT_EVENT_QUEUE_SIZE
from .thread_util import THREAD_JOIN_TIMEOUT


@dataclass
class BatchEventLogs:
    payload: dict
    headers: dict
    event_count: int
    retries: int = 0


_DIAGNOSTICS_EVENT = "statsig::diagnostics"


class EventBatchProcessor:
    def __init__(self, options: StatsigOptions, statsig_metadata: dict, shutdown_event, error_boundary, diagnostics):
        self._local_mode = options.local_mode
        self._diagnostics = diagnostics
        self._lock = threading.Lock()
        self._batch_size = options.event_queue_size
        self._event_array: List[Dict] = []
        self._batched_events_queue: Deque[BatchEventLogs] = deque(maxlen=options.retry_queue_size)
        self._statsig_metadata = statsig_metadata
        self._shutdown_event = shutdown_event
        self._batching_interval = globals.STATSIG_BATCHING_INTERVAL_SECONDS
        self._error_boundary = error_boundary
        self._batching_thread = None
        self._dropped_events_count = 0
        self._dropped_events_count_logging_thread = None

    def add_to_batched_events_queue(self, batched_events):
        with self._lock:
            if self._batched_events_queue.maxlen is not None and len(
                    self._batched_events_queue) >= self._batched_events_queue.maxlen:
                self._dropped_events_count += self._batched_events_queue[0].event_count
            self._batched_events_queue.append(batched_events)

    def get_batched_event(self):
        with self._lock:
            if len(self._batched_events_queue) > 0:
                return self._batched_events_queue.popleft()
            return None

    def get_dropped_event_count(self):
        with self._lock:
            count = self._dropped_events_count
            self._dropped_events_count = 0
            return count

    def batch_events(self, add_to_queue=True):
        batched_event = None
        self._add_diagnostics_event(Context.API_CALL)
        self._add_diagnostics_event(Context.LOG_EVENT)
        with self._lock:
            if len(self._event_array) > 0:
                batched_event = BatchEventLogs(
                    payload={
                        "events": self._event_array.copy(),
                        "statsigMetadata": self._statsig_metadata
                    },
                    headers={"STATSIG-EVENT-COUNT": str(len(self._event_array))},
                    event_count=len(self._event_array),
                    retries=0
                )
                self._event_array.clear()
        if batched_event is not None and add_to_queue:
            self.add_to_batched_events_queue(batched_event)
        return batched_event

    def add_event(self, event):
        should_batch = False
        batched_event = None
        with self._lock:
            self._event_array.append(event)
            batch_size = self._check_batch_array_size_interval() or self._batch_size
            if len(self._event_array) >= batch_size:
                should_batch = True
                batched_event = BatchEventLogs(
                    payload={
                        "events": self._event_array.copy(),
                        "statsigMetadata": self._statsig_metadata
                    },
                    headers={"STATSIG-EVENT-COUNT": str(len(self._event_array))},
                    event_count=len(self._event_array),
                    retries=0
                )
                self._event_array.clear()

        if should_batch and batched_event is not None:
            self.add_to_batched_events_queue(batched_event)

    def get_all_batched_events(self):
        self.batch_events()
        with self._lock:
            copy_events = list(self._batched_events_queue)
            return copy_events

    def shutdown(self):
        if self._batching_thread is not None:
            self._batching_thread.join(THREAD_JOIN_TIMEOUT)
        if self._dropped_events_count_logging_thread is not None:
            self._dropped_events_count_logging_thread.join(THREAD_JOIN_TIMEOUT)

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
        self.add_event(event.to_dict())

    def _check_batch_array_size_interval(self):
        try:
            override_queue_size = _SDK_Configs.get_config_num_value("event_queue_size")
            if override_queue_size is not None:
                override_queue_size = int(override_queue_size)
                if override_queue_size > 0 and override_queue_size != DEFAULT_EVENT_QUEUE_SIZE:
                    return override_queue_size
            return None
        except Exception:
            return None
