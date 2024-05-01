class FeatureGate:
    def __init__(self, data, name, rule, group_name=None):
        self.value = False if data is None else data
        self.name = "" if name is None  else name
        self.rule_id = "" if rule is None else rule
        self.group_name = group_name

    def get_value(self):
        """Returns the underlying value of this FeatureGate"""
        return self.value

    def get_name(self):
        """Returns the name of this FeatureGate"""
        return self.name
