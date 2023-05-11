import time
from enum import Enum


class Context(Enum):
    INITIALIZE = "initialize"
    CONFIG_SYNC = "config_sync"


class Marker:
    def __init__(self, key, action, step, value):
        if key is None:
            key = ""
        self.key = key
        self.action = action
        self.step = step
        self.value = value
        self.timestamp = round(time.time() * 1000)

    def serialize(self) -> object:
        return {
            "key": self.key,
            "step": self.step,
            "action": self.action,
            "value": self.value,
            "timestamp": self.timestamp,
        }


class _Diagnostics:
    def __init__(self):
        self.markers = {
            'initialize': [],
            'config_sync': [],
        }

    def mark(self, context: Context, key, action, step=None, value=None):
        marker = Marker(key, action, step, value)
        self.markers[context].append(marker)

    def serialize_context(self, context: Context) -> object:
        return {
            "markers": [marker.serialize() for marker in self.markers[context]],
            "context": context
        }

    def clear_markers(self, context: Context):
        if self.markers.get(context) is None:
            return
        self.markers[context] = []

    def create_tracker(self, context: Context, key, step=None):
        return MarkerTracker(self, context, key, step)


class MarkerTracker:
    def __init__(self, diagnostics, context: Context, key, step=None):
        self.diagnostics = diagnostics
        self.context = context
        self.key = key
        self.step = step

    def mark(self, data):
        action = data.get('action', None)
        value = data.get("value", None)
        step = data.get("step", self.step)

        self.diagnostics.mark(self.context, self.key, action, step, value)

    def mark_end(self, data=None):
        if data is None:
            data = {}
        data['action'] = 'end'
        self.mark(data)

    def mark_start(self, data=None):
        if data is None:
            data = {}
        data['action'] = 'start'
        self.mark(data)

    def set_step(self, step):
        self.step = step
