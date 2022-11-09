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

    def get(self, key, default=None):
        """Returns the value of the config at the given key
        or the provided default if the key is not found
        """
        return self.value.get(key, default)

    def get_typed(self, key, default=None):
        """Returns the value of the config at the given key
        iff the type matches the type of the provided default.
        Otherwise, returns the default value
        """
        res = self.value.get(key, default)
        if default is None:
            return res
        if not isinstance(default, type(res)):
            return default
        return res

    def get_value(self):
        """Returns the underlying value of this DynamicConfig"""
        return self.value

    def get_name(self):
        """Returns the name of this DynamicConfig"""
        return self.name
