import json

class StatsigEvent:
    def __init__(self, user, event_name):
        self.user = user
        self.event_name = event_name
        self.value = None
        self.metadata = None
        self._secondary_exposures = None

    def to_dict(self):
        evt_nullable = {
            'user': None if self.user is None else self.user.to_dict(),
            'eventName': self.event_name,
            'value': self.value,
            'metadata': self.metadata,
            'secondaryExposures': self._secondary_exposures,
        }
        return {k: v for k, v in evt_nullable.items() if v is not None}