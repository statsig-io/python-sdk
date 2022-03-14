class Layer:
    def __init__(self, data, name, rule):
        if data is None:
            data = {}
        self.__value = data
        if name is None:
            name = ""
        self.name = name
        if rule is None:
            rule = ""
        self.rule_id = rule

    def get(self, key, default=None):
        """Returns the value of the layer at the given key
        or the provided default if the key is not found
        """
        return self.__value.get(key, default)

    def get_typed(self, key, default=None):
        """Returns the value of the layer at the given key
        iff the type matches the type of the provided default.
        Otherwise, returns the default value
        """
        res = self.__value.get(key, default)
        if default is None:
            return res
        if type(default) != type(res):
            return default
        return res

    def get_name(self):
        """Returns the name of this Layer"""
        return self.name
