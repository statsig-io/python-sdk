import threading

from . import globals
from .thread_util import spawn_background_thread


class TTLSet:
    def __init__(self, shutdown_event):
        self.store = set()
        self.lock = threading.Lock()
        self.reset_interval = 60
        self.shutdown_event = shutdown_event
        self.start_reset_thread()

    def add(self, key):
        with self.lock:
            self.store.add(key)

    def contains(self, key):
        with self.lock:
            return key in self.store

    def reset(self):
        with self.lock:
            self.store.clear()

    def start_reset_thread(self):
        """Starts a thread to reset the set every minute."""

        def reset_worker():
            while True:
                try:
                    if self.shutdown_event.wait(self.reset_interval):
                        break
                    self.reset()
                except Exception as e:
                    globals.logger.debug(f"Failed to reset TTL set: {e}")

        spawn_background_thread("reset ttl set worker", reset_worker, ())
