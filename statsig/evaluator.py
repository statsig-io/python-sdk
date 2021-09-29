class ConfigEvaluation:

    def __init__(self, fetch_from_server = False, boolean_value = False, json_value = None, rule_id = None):
        self.fetch_from_server = fetch_from_server
        self.boolean_value = boolean_value
        self.json_value = json_value
        self.rule_id = rule_id


class Evaluator:
    def __init__(self):
        print('Evaluator')
        self.configs = dict()
        self.gates = dict()

    def setDownloadedConfigs(self, configs):
        for gate in configs["feature_gates"]:
            self.gates[gate["name"]] = gate
        for config in configs["dynamic_configs"]:
            self.gates[config["name"]] = gate

    def check_gate(self, user, gate):
        return ConfigEvaluation(False, False, None, None)
    
    def get_config(self, user, config):
        return ConfigEvaluation(False, False, {}, None)
