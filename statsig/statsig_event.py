import json

class StatsigEvent:
    def __init__(self, user, event_name):
        self.user = user
        self.event_name = event_name
        self.value = None
        self.metadata = None

    def to_json_string(self):
        evt_nullable = {
            'user': None if self.user is None else self.user.to_dict(),
            'eventName': self.event_name,
            'value': self.value,
            'metadata': self.metadata,
        }
        evt = {}
        for key in evt_nullable:
            if not evt_nullable[key] is None:
                evt[key] = evt_nullable[key]
        return json.dumps(evt)