import json

class StatsigOptions:
    def __init__(self):
        self.api = None
        self.environment = None

    def to_json_string(self):
        options_nullable = {
            'api': self.api,
            'environment': self.environment,
        }
        options = {}
        for key in options_nullable:
            if not options_nullable[key] is None:
                options[key] = options_nullable[key]
        return json.dumps(options)