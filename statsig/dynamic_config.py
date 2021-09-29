import json

class DynamicConfig:
    def __init__(self, data, name, rule):
        self.value = data
        self.name = name
        self.rule_id = rule
    
    def get_value(self):
        return self.value
    
    def get_name(self):
        return self.name