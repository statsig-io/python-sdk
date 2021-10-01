import time
from datetime import datetime
import re
from hashlib import sha256
from struct import unpack

class ConfigEvaluation:

    def __init__(self, fetch_from_server = False, boolean_value = False, json_value = {}, rule_id = None):
        self.fetch_from_server = fetch_from_server
        self.boolean_value = boolean_value
        self.json_value = json_value
        self.rule_id = rule_id


class Evaluator:
    def __init__(self):
        self.configs = dict()
        self.gates = dict()

    def setDownloadedConfigs(self, configs):
        for gate in configs["feature_gates"]:
            self.gates[gate["name"]] = gate
        for config in configs["dynamic_configs"]:
            self.gates[config["name"]] = gate

    def check_gate(self, user, gate):
        if gate not in self.gates:
            return ConfigEvaluation()
        return self._evaluate(user, self.gates[gate])
    
    def get_config(self, user, config):
        if config not in self.configs:
            return ConfigEvaluation()
        
        return self._evaluate(user, self.configs[config])

    def _evaluate(self, user, config):
        if not config["enabled"]:
            return ConfigEvaluation(False, False, config["defaultValue"])
        for rule in config["rules"]:
            result = self._evaluate_rule(user, rule)
            if result.boolean_value:
                user_passes = self._eval_pass_percentage(user, rule, config)
                config = rule["returnValue"] if user_passes else config["defaultValue"]
                return ConfigEvaluation(False, user_passes, config, rule["id"])
        
        return ConfigEvaluation(False, False, config["defaultValue"], "default")
    
    def _evaluate_rule(self, user, rule):
        for condition in rule["conditions"]:
            result = self._evaluate_condition(user, condition)
            if result.fetch_from_server:
                return result
            if not result.boolean_value:
                return ConfigEvaluation(False, False, rule["returnValue"], rule["id"])
        return ConfigEvaluation(False, True, rule["returnValue"], rule["id"])
    
    def _evaluate_condition(self, user, condition):
        value = None
        type = condition["type"].upper()
        if type == "PUBLIC":
            return ConfigEvaluation(False, True)
        elif type == "FAIL_GATE" or type == "PASS_GATE":
            other_result = self.check_gate(user, condition["targetValue"])
            if (other_result.fetch_from_server):
                return ConfigEvaluation(True)
            pass_gate = other_result.boolean_value if type == "PASS_GATE" else not other_result.boolean_value
            return ConfigEvaluation(other_result.fetch_from_server, pass_gate)
        elif type == "IP_BASED":
            ## TODO
            return ConfigEvaluation(True)
        elif type == "UA_BASED":
            value = self._get_from_user(user, condition["field"])
            ## TODO
        elif type == "USER_FIELD":
            value = self._get_from_user(user, condition["field"])
        elif type == "CURRENT_TIME":
            value = round(time.time() * 1000)
        elif type == "ENVIRONMENT_FIELD":
            value = self._get_from_environment(user, condition["field"])
        elif type == "USER_BUCKET":
            salt = self._get_value_as_string(condition["additionalValues"]["salt"])
            user_id = user.user_id if user.user_id is not None else ''
            value = int(self._compute_user_hash(salt + "." + user_id) % 1000)
        else:
            return ConfigEvaluation(True)

        op = condition["operator"]
        if op == "gt":
            val = self._get_value_as_float(value)
            target = self._get_value_as_float(condition["targetValue"])
            if val is None or target is None:
                return ConfigEvaluation(False, False)
            return ConfigEvaluation(False, val > target)
        elif op == "gte":
            val = self._get_value_as_float(value)
            target = self._get_value_as_float(condition["targetValue"])
            if val is None or target is None:
                return ConfigEvaluation(False, False)
            return ConfigEvaluation(False, val >= target)
        elif op == "lt":
            val = self._get_value_as_float(value)
            target = self._get_value_as_float(condition["targetValue"])
            if val is None or target is None:
                return ConfigEvaluation(False, False)
            return ConfigEvaluation(False, val < target)
        elif op == "lte":
            val = self._get_value_as_float(value)
            target = self._get_value_as_float(condition["targetValue"])
            if val is None or target is None:
                return ConfigEvaluation(False, False)
            return ConfigEvaluation(False, val <= target)
        elif op == "version_gt":
            res = self._version_compare_helper(value, condition["targetValue"], lambda a,b: self._version_compare(a, b) > 0)
            return ConfigEvaluation(False, res)
        elif op == "version_gte":
            res = self._version_compare_helper(value, condition["targetValue"], lambda a,b: self._version_compare(a, b) >= 0)
            return ConfigEvaluation(False, res)
        elif op == "version_lt":
            res = self._version_compare_helper(value, condition["targetValue"], lambda a,b: self._version_compare(a, b) < 0)
            return ConfigEvaluation(False, res)
        elif op == "version_lte":
            res = self._version_compare_helper(value, condition["targetValue"], lambda a,b: self._version_compare(a, b) <= 0)
            return ConfigEvaluation(False, res)
        elif op == "version_eq":
            res = self._version_compare_helper(value, condition["targetValue"], lambda a,b: self._version_compare(a, b) == 0)
            return ConfigEvaluation(False, res)
        elif op == "version_neq":
            res = self._version_compare_helper(value, condition["targetValue"], lambda a,b: self._version_compare(a, b) != 0)
            return ConfigEvaluation(False, res)
        elif op == "any":
            return ConfigEvaluation(False, self._match_string_in_array(value, condition["targetValue"], lambda a,b: a.upper().lower() == b.upper().lower()))
        elif op == "none":
            return ConfigEvaluation(False, not self._match_string_in_array(value, condition["targetValue"], lambda a,b: a.upper().lower() == b.upper().lower()))
        elif op == "any_case_sensitive":
            return ConfigEvaluation(False, self._match_string_in_array(value, condition["targetValue"], lambda a,b: a == b))
        elif op == "none_case_sensitive":
            return ConfigEvaluation(False, not self._match_string_in_array(value, condition["targetValue"], lambda a,b: a == b))
        elif op == "str_starts_with_any":
            return ConfigEvaluation(False, self._match_string_in_array(value, condition["targetValue"], lambda a,b: a.upper().lower().startswith(b.upper().lower())))
        elif op == "str_ends_with_any":
            return ConfigEvaluation(False, self._match_string_in_array(value, condition["targetValue"], lambda a,b: a.upper().lower().endswith(b.upper().lower())))
        elif op == "str_contains_any":
            return ConfigEvaluation(False, self._match_string_in_array(value, condition["targetValue"], lambda a,b: b.upper().lower() in a.upper().lower()))
        elif op == "str_contains_none":
            return ConfigEvaluation(False, not self._match_string_in_array(value, condition["targetValue"], lambda a,b: b.upper().lower() in a.upper().lower()))
        elif op == "str_matches":
            str_value = self._get_value_as_string(value)
            str_target = self._get_value_as_string(condition["targetValue"])
            if str_value == None or str_target == None:
                return ConfigEvaluation(False, False)
            return ConfigEvaluation(False, bool(re.match(str_target, str_value)))
        elif op == "eq":
            return ConfigEvaluation(False, value == condition["targetValue"])
        elif op == "neq":
            return ConfigEvaluation(False, value != condition["targetValue"])
        elif op == "before":
            return self._compare_dates(value, condition["targetValue"], lambda a, b: a.date() < b.date())
        elif op == "after":
            return self._compare_dates(value, condition["targetValue"], lambda a, b: a.date() > b.date())
        elif op == "on":
            return self._compare_dates(value, condition["targetValue"], lambda a, b: a.date() == b.date())

        return ConfigEvaluation(True)


    def _get_from_user(self, user, field):
        value = None
        lower_field = field.lower()
        if lower_field == "userid" or lower_field == "user_id":
            value = user.user_id
        elif lower_field == "email":
            value = user.email
        elif lower_field == "ip" or lower_field == "ipaddress" or lower_field == "ip_address":
            value = user.ip_address
        elif lower_field == "useragent" or lower_field == "user_agent":
            value = user.user_agent
        elif lower_field == "country":
            value = user.country
        elif lower_field == "locale":
            value = user.locale
        elif lower_field == "appversion" or lower_field == "app_version":
            value = user.app_version
        
        if (value == None or value == "") and user.custom is not None:
            if field in user.custom:
                value = user.custom[field]
            elif field.upper().lower() in user.custom:
                value = user.custom[field.upper().lower()]

        if (value == None or value == "") and user.private_attributes is not None:
            if field in user.private_attributes:
                value = user.private_attributes[field]
            elif field.lower() in user.private_attributes:
                value = user.private_attributes[field.lower()]

        return value
    
    def _get_from_environment(self, user, field):
        if user.statsig_environment is None:
            return None
        if field in user.statsig_environment:
            return user.statsig_environment[field]
        elif field.lower() in user.statsig_environment:
            return user.statsig_environment[field]
        return None

    def _compute_user_hash(self, input):
        return unpack('>Q', sha256(str(input).encode('utf-8')).digest()[:8])[0]
    
    def _eval_pass_percentage(self, user, rule, config):
        rule_salt = rule["salt"] if "salt" in rule else rule["id"]
        id = user.user_id if user.user_id is not None else ""
        hash = self._compute_user_hash(
            config["salt"] + "." + rule_salt + "." + id
        )
        return (hash % 10000) < rule["passPercentage"] * 100

    def _match_string_in_array(self, value, target, compare):
        str_value = self._get_value_as_string(value)
        if str_value is None:
            return False
        for match in target:
            str_match = self._get_value_as_string(match)
            if str_match is None:
                continue
            if compare(str_value, str_match):
                return True
        return False

    def _version_compare(self, v1, v2):
        p1 = v1.split(".")
        p2 = v2.split(".")

        i = 0
        while i < max(len(p1), len(p2)):
            c1 = 0
            c2 = 0
            if i < len(p1):
                c1 = int(float(p1[i]))
            if i < len(p2):
                c2 = int(float(p2[i]))
            if c1 < c2:
                return -1
            elif c1 > c2:
                return 1
            i += 1

        return 0

    def _version_compare_helper(self, v1, v2, compare):
        v1_str = self._get_value_as_string(v1)
        v2_str = self._get_value_as_string(v2)

        if v1_str is None or v2_str is None:
            return False
        
        d1 = v1_str.find('-')
        if d1 > 0:
            v1_str = v1_str[0:d1]
        
        d2 = v2_str.find('-')
        if d2 > 0:
            v2_str = v2_str[0:d2]
        
        return compare(v1_str, v2_str)

    def _get_value_as_string(self, input):
        if input is None:
            return None
        return str(input)
    
    def _get_value_as_float(self, input):
        if input is None:
            return None
        return float(input)
    
    def _contains(self, targets, value, ignore_case):
        if targets is None or value is None:
            return False
        
        for option in targets:
            if ignore_case:
                if option.upper().lower() == value.upper().lower():
                    return True
            if option == value:
                return True
        return False

    def _get_from_user_agent(self, user, field):
        # TODO
        return None

    def _compare_dates(self, first, second, compare):
        if first is None and second is None:
            return ConfigEvaluation(False, False)

        first_date = self._get_date(first)
        second_date = self._get_date(second)
        if first_date is None or second_date is None:
            return ConfigEvaluation(False, False)

        return ConfigEvaluation(
            False,
            compare(first_date, second_date)
        )
    
    def _get_date(self, d):
        if d is None:
            return None
        
        epoch = int(d)
        if len(str(d)) >= 11:
            epoch /= 1000
            
        return datetime.fromtimestamp(epoch)
