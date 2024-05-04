from .evaluation_details import EvaluationDetails, EvaluationReason


class _ConfigEvaluation:

    def __init__(self,
                 boolean_value=False,
                 json_value=None,
                 rule_id="",
                 secondary_exposures=None,
                 allocated_experiment=None,
                 explicit_parameters=None,
                 is_experiment_group=False,
                 evaluation_details=None,
                 group_name=None):
        if boolean_value is None:
            boolean_value = False
        self.boolean_value = boolean_value
        if json_value is None:
            json_value = {}
        self.json_value = json_value
        if rule_id is None:
            rule_id = ""
        self.rule_id = rule_id
        if secondary_exposures is None:
            secondary_exposures = []
        if explicit_parameters is None:
            explicit_parameters = []
        self.secondary_exposures = secondary_exposures
        self.undelegated_secondary_exposures = self.secondary_exposures
        self.allocated_experiment = allocated_experiment
        self.explicit_parameters = explicit_parameters
        self.is_experiment_group = is_experiment_group is True
        if evaluation_details is None:
            evaluation_details = EvaluationDetails(0, 0, EvaluationReason.unrecognized)
        self.evaluation_details = evaluation_details
        self.group_name = group_name
