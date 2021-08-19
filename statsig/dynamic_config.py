import json

class DynamicConfig:
    def __init__(self, jsonString):
        config = json.loads(jsonString)
        self.value = {} if config['value'] is None else config['value']
        self.name = config['name']
        self.rule_id = config['rule_id']
    
    def getValue(self):
        return self.value
    
    def getName(self):
        return self.name