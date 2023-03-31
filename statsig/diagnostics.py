import time


class _Diagnostics:
    def __init__(self, context):
        self.context = context
        self.markers = []

    def mark(self, key, action, step=None, value=None):
        marker = Marker(key, action, step, value)
        self.markers.append(marker)

    def serialize(self) -> object:
        return {
            "markers": [marker.serialize() for marker in self.markers],
            "context": self.context
        }


class Marker:
    def __init__(self, key, action, step, value):
        if key is None:
            key = ""
        self.key = key
        self.action = action
        self.step = step
        self.value = value
        self.timestamp = round(time.time()*1000)

    def serialize(self) -> object:
        return {
            "key": self.key,
            "step": self.step,
            "action": self.action,
            "value": self.value,
            "timestamp": self.timestamp,
        }
