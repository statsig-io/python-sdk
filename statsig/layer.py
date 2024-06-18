from typing import Callable, Optional


class Layer:
    __create_key = object()

    @classmethod
    def _create(cls, name: str, value: dict, rule: str, group_name=None,
                allocated_experiment=None, param_log_func=None, evaluation_details=None):
        return Layer(
            cls.__create_key, name, value, rule, group_name, allocated_experiment,
            param_log_func, evaluation_details=evaluation_details)

    def __init__(self, create_key, name: str, value: dict, rule: str,
                 group_name: Optional[str],
                 allocated_experiment: Optional[str],
                 param_log_func: Callable[['Layer', str], None],
                 evaluation_details=None):
        assert (create_key == Layer.__create_key), \
            "Layers should only be created internally by Statsig"

        self.__log_func = param_log_func
        if value is None:
            value = {}
        self.__value = value
        if name is None:
            name = ""
        self.name = name
        if rule is None:
            rule = ""
        self.rule_id = rule
        self.group_name = group_name
        self.allocated_experiment = allocated_experiment
        self.evaluation_details = evaluation_details

    def get(self, key, default=None):
        """Returns the value of the layer at the given key
        or the provided default if the key is not found
        """
        result = self.__value.get(key, None)
        if result is not None:
            self._log_parameter_exposure(key)
            return result

        return default

    def get_typed(self, key, default=None):
        """Returns the value of the layer at the given key
        iff the type matches the type of the provided default.
        Otherwise, returns the default value
        """
        res = self.__value.get(key, None)
        if default is not None and not isinstance(default, type(res)):
            return default

        if res is not None:
            self._log_parameter_exposure(key)
            return res

        return default

    def get_name(self):
        """Returns the name of this Layer"""
        return self.name

    def get_values(self):
        """Returns all the values in this Layer but does not trigger an exposure log"""
        return self.__value

    def _log_parameter_exposure(self, parameter_name: str):
        if self.__log_func is None:
            return

        self.__log_func(self, parameter_name)

    def get_evaluation_details(self):
        """Returns the evaluation detail of this Layer"""
        return self.evaluation_details
