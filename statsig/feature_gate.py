class FeatureGate:
    def __init__(self, data, name, rule, group_name=None, evaluation_details=None):
        self.value = False if data is None else data
        self.name = "" if name is None  else name
        self.rule_id = "" if rule is None else rule
        self.group_name = group_name
        self.evaluation_details = evaluation_details

    def get_value(self):
        """Returns the underlying value of this FeatureGate"""
        return self.value

    def get_name(self):
        """Returns the name of this FeatureGate"""
        return self.name

    def get_evaluation_details(self):
        """Returns the evaluation detail of this FeatureGate"""
        return self.evaluation_details
