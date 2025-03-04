from .evaluation_details import EvaluationDetails, EvaluationReason, DataSource


class _ConfigEvaluation:

    def __init__(self,
                 boolean_value=False,
                 json_value=None,
                 rule_id="",
                 version=None,
                 secondary_exposures=None,
                 allocated_experiment=None,
                 explicit_parameters=None,
                 is_experiment_group=False,
                 evaluation_details=None,
                 group_name=None,
                 sample_rate=None,
                 user=None,
                 forward_all_exposures=False,
                 id_type="",
                 analytical_condition=False,
                 seen_analytical_gates=False
        ):
        if boolean_value is None:
            boolean_value = False
        self.boolean_value = boolean_value
        if json_value is None:
            json_value = {}
        self.json_value = json_value
        if rule_id is None:
            rule_id = ""
        self.rule_id = rule_id
        self.id_type = id_type
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
            evaluation_details = EvaluationDetails(0, 0, DataSource.UNINITIALIZED, EvaluationReason.none)
        self.evaluation_details = evaluation_details
        self.group_name = group_name
        self.sample_rate = sample_rate
        self.user = user
        self.forward_all_exposures = forward_all_exposures
        self.version = version
        self.analytical_condition = analytical_condition
        self.seen_analytical_gates = seen_analytical_gates
