import json

class DynamicConfig:
    def __init__(self, jsonString):
        config = json.loads(jsonString)
        self.value = {} if config['value'] is None else config['value']
        self.name = config['name']
        self.rule_id = config['rule_id']
    
    def get_value(self):
        return self.value
    
    def get_name(self):
        return self.name