class DynamicConfig:
    def __init__(self, data, name, rule):
        if data is None:
            data = {}
        self.value = data
        if name is None:
            name = ""
        self.name = name
        if rule is None:
            rule = ""
        self.rule_id = rule
    
    def get_value(self):
        return self.value
    
    def get_name(self):
        return self.name
    