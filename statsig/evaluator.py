import time
from datetime import datetime
import re
from hashlib import sha256
from struct import unpack
from ua_parser import user_agent_parser
from ip3country import CountryLookup

class _ConfigEvaluation:

    def __init__(self, fetch_from_server = False, boolean_value = False, json_value = {}, rule_id = None, secondary_exposures = []):
        self.fetch_from_server = fetch_from_server
        self.boolean_value = boolean_value
        self.json_value = json_value
        self.rule_id = rule_id
        self.secondary_exposures = secondary_exposures

class _Evaluator:
    def __init__(self):
        self._configs = dict()
        self._gates = dict()
        self._country_lookup = CountryLookup()

    def setDownloadedConfigs(self, configs):
        if "feature_gates" in configs:
            self._gates = dict()
            for gate in configs["feature_gates"]:
                self._gates[gate["name"]] = gate
        if "dynamic_configs" in configs:
            self._configs = dict()
            for config in configs["dynamic_configs"]:
                self._configs[config["name"]] = config

    def check_gate(self, user, gate):
        if gate not in self._gates:
            return _ConfigEvaluation()
        return self.__evaluate(user, self._gates[gate])
    
    def get_config(self, user, config):
        if config not in self._configs:
            return _ConfigEvaluation()
        
        return self.__evaluate(user, self._configs[config])

    def __evaluate(self, user, config):
        exposures = []
        if not config["enabled"]:
            return _ConfigEvaluation(False, False, config["defaultValue"], "disabled", exposures)
        
        for rule in config["rules"]:
            result = self.__evaluate_rule(user, rule)
            if result.fetch_from_server:
                return result
            if result.secondary_exposures is not None and len(result.secondary_exposures) > 0:
                exposures = exposures + result.secondary_exposures
            if result.boolean_value:
                user_passes = self.__eval_pass_percentage(user, rule, config)
                config = rule["returnValue"] if user_passes else config["defaultValue"]
                return _ConfigEvaluation(False, user_passes, config, rule["id"], exposures)
        return _ConfigEvaluation(False, False, config["defaultValue"], "default", exposures)
    
    def __evaluate_rule(self, user, rule):
        exposures = []
        eval_result = True
        for condition in rule["conditions"]:
            result = self.__evaluate_condition(user, condition)
            if result.fetch_from_server:
                return result
            if result.secondary_exposures is not None and len(result.secondary_exposures) > 0:
                exposures = exposures + result.secondary_exposures
            if not result.boolean_value:
                eval_result = False
        return _ConfigEvaluation(False, eval_result, rule["returnValue"], rule["id"], exposures)
    
    def __evaluate_condition(self, user, condition):
        value = None
        type = condition["type"].upper()
        if type == "PUBLIC":
            return _ConfigEvaluation(False, True)
        elif type == "FAIL_GATE" or type == "PASS_GATE":
            other_result = self.check_gate(user, condition["targetValue"])
            if (other_result.fetch_from_server):
                return _ConfigEvaluation(True)
            new_exposure = {
                "gate": condition["targetValue"],
                "gateValue": "true" if other_result.boolean_value else "false",
                "ruleID": other_result.rule_id
            }
            exposures = [new_exposure]
            if other_result.secondary_exposures is not None and len(other_result.secondary_exposures) > 0:
                exposures = other_result.secondary_exposures + exposures
            pass_gate = other_result.boolean_value if type == "PASS_GATE" else not other_result.boolean_value
            return _ConfigEvaluation(other_result.fetch_from_server, pass_gate, {}, None, exposures)
        elif type == "IP_BASED":
            value = self.__get_from_user(user, condition["field"])
            if value is None:
                ip = self.__get_from_user(user, "ip")
                if ip is not None and condition["field"] == "country":
                    value = self._country_lookup.lookupStr(ip)
            if value is None:
                return _ConfigEvaluation(False, False)
        elif type == "UA_BASED":
            value = self.__get_from_user_agent(user, condition["field"])
        elif type == "USER_FIELD":
            value = self.__get_from_user(user, condition["field"])
        elif type == "CURRENT_TIME":
            value = round(time.time() * 1000)
        elif type == "ENVIRONMENT_FIELD":
            value = self.__get_from_environment(user, condition["field"])
        elif type == "USER_BUCKET":
            salt = self.__get_value_as_string(condition["additionalValues"]["salt"])
            user_id = user.user_id if user.user_id is not None else ''
            value = int(self.__compute_user_hash(salt + "." + user_id) % 1000)
        else:
            return _ConfigEvaluation(True)

        op = condition["operator"]
        if op == "gt":
            val = self.__get_value_as_float(value)
            target = self.__get_value_as_float(condition["targetValue"])
            if val is None or target is None:
                return _ConfigEvaluation(False, False)
            return _ConfigEvaluation(False, val > target)
        elif op == "gte":
            val = self.__get_value_as_float(value)
            target = self.__get_value_as_float(condition["targetValue"])
            if val is None or target is None:
                return _ConfigEvaluation(False, False)
            return _ConfigEvaluation(False, val >= target)
        elif op == "lt":
            val = self.__get_value_as_float(value)
            target = self.__get_value_as_float(condition["targetValue"])
            if val is None or target is None:
                return _ConfigEvaluation(False, False)
            return _ConfigEvaluation(False, val < target)
        elif op == "lte":
            val = self.__get_value_as_float(value)
            target = self.__get_value_as_float(condition["targetValue"])
            if val is None or target is None:
                return _ConfigEvaluation(False, False)
            return _ConfigEvaluation(False, val <= target)
        elif op == "version_gt":
            res = self.__version_compare_helper(value, condition["targetValue"], lambda a,b: self.__version_compare(a, b) > 0)
            return _ConfigEvaluation(False, res)
        elif op == "version_gte":
            res = self.__version_compare_helper(value, condition["targetValue"], lambda a,b: self.__version_compare(a, b) >= 0)
            return _ConfigEvaluation(False, res)
        elif op == "version_lt":
            res = self.__version_compare_helper(value, condition["targetValue"], lambda a,b: self.__version_compare(a, b) < 0)
            return _ConfigEvaluation(False, res)
        elif op == "version_lte":
            res = self.__version_compare_helper(value, condition["targetValue"], lambda a,b: self.__version_compare(a, b) <= 0)
            return _ConfigEvaluation(False, res)
        elif op == "version_eq":
            res = self.__version_compare_helper(value, condition["targetValue"], lambda a,b: self.__version_compare(a, b) == 0)
            return _ConfigEvaluation(False, res)
        elif op == "version_neq":
            res = self.__version_compare_helper(value, condition["targetValue"], lambda a,b: self.__version_compare(a, b) != 0)
            return _ConfigEvaluation(False, res)
        elif op == "any":
            return _ConfigEvaluation(False, self.__match_string_in_array(value, condition["targetValue"], lambda a,b: a.upper().lower() == b.upper().lower()))
        elif op == "none":
            return _ConfigEvaluation(False, not self.__match_string_in_array(value, condition["targetValue"], lambda a,b: a.upper().lower() == b.upper().lower()))
        elif op == "any_case_sensitive":
            return _ConfigEvaluation(False, self.__match_string_in_array(value, condition["targetValue"], lambda a,b: a == b))
        elif op == "none_case_sensitive":
            return _ConfigEvaluation(False, not self.__match_string_in_array(value, condition["targetValue"], lambda a,b: a == b))
        elif op == "str_starts_with_any":
            return _ConfigEvaluation(False, self.__match_string_in_array(value, condition["targetValue"], lambda a,b: a.upper().lower().startswith(b.upper().lower())))
        elif op == "str_ends_with_any":
            return _ConfigEvaluation(False, self.__match_string_in_array(value, condition["targetValue"], lambda a,b: a.upper().lower().endswith(b.upper().lower())))
        elif op == "str_contains_any":
            return _ConfigEvaluation(False, self.__match_string_in_array(value, condition["targetValue"], lambda a,b: b.upper().lower() in a.upper().lower()))
        elif op == "str_contains_none":
            return _ConfigEvaluation(False, not self.__match_string_in_array(value, condition["targetValue"], lambda a,b: b.upper().lower() in a.upper().lower()))
        elif op == "str_matches":
            str_value = self.__get_value_as_string(value)
            str_target = self.__get_value_as_string(condition["targetValue"])
            if str_value == None or str_target == None:
                return _ConfigEvaluation(False, False)
            return _ConfigEvaluation(False, bool(re.match(str_target, str_value)))
        elif op == "eq":
            return _ConfigEvaluation(False, value == condition["targetValue"])
        elif op == "neq":
            return _ConfigEvaluation(False, value != condition["targetValue"])
        elif op == "before":
            return self.__compare_dates(value, condition["targetValue"], lambda a, b: a.date() < b.date())
        elif op == "after":
            return self.__compare_dates(value, condition["targetValue"], lambda a, b: a.date() > b.date())
        elif op == "on":
            return self.__compare_dates(value, condition["targetValue"], lambda a, b: a.date() == b.date())

        return _ConfigEvaluation(True)


    def __get_from_user(self, user, field):
        value = None
        lower_field = field.lower()
        if lower_field == "userid" or lower_field == "user_id":
            value = user.user_id
        elif lower_field == "email":
            value = user.email
        elif lower_field == "ip" or lower_field == "ipaddress" or lower_field == "ip_address":
            value = user.ip
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
    
    def __get_from_environment(self, user, field):
        if user._statsig_environment is None:
            return None
        if field in user._statsig_environment:
            return user._statsig_environment[field]
        elif field.lower() in user._statsig_environment:
            return user._statsig_environment[field]
        return None

    def __compute_user_hash(self, input):
        return unpack('>Q', sha256(str(input).encode('utf-8')).digest()[:8])[0]
    
    def __eval_pass_percentage(self, user, rule, config):
        rule_salt = rule["salt"] if "salt" in rule else rule["id"]
        id = user.user_id if user.user_id is not None else ""
        hash = self.__compute_user_hash(
            config["salt"] + "." + rule_salt + "." + id
        )
        return (hash % 10000) < rule["passPercentage"] * 100

    def __match_string_in_array(self, value, target, compare):
        str_value = self.__get_value_as_string(value)
        if str_value is None:
            return False
        for match in target:
            str_match = self.__get_value_as_string(match)
            if str_match is None:
                continue
            if compare(str_value, str_match):
                return True
        return False

    def __version_compare(self, v1, v2):
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

    def __version_compare_helper(self, v1, v2, compare):
        v1_str = self.__get_value_as_string(v1)
        v2_str = self.__get_value_as_string(v2)

        if v1_str is None or v2_str is None:
            return False
        
        d1 = v1_str.find('-')
        if d1 > 0:
            v1_str = v1_str[0:d1]
        
        d2 = v2_str.find('-')
        if d2 > 0:
            v2_str = v2_str[0:d2]
        
        return compare(v1_str, v2_str)

    def __get_value_as_string(self, input):
        if input is None:
            return None
        return str(input)
    
    def __get_value_as_float(self, input):
        if input is None:
            return None
        return float(input)

    def __get_from_user_agent(self, user, field):
        ua = self.__get_from_user(user, "userAgent")
        if ua is None:
            return None
        parsed = user_agent_parser.Parse(ua)
        field = field.lower()
        if (field == "os" or field == "os_name") and "os" in parsed and "family" in parsed["os"]:
            return parsed["os"]["family"]
        elif (field == "os_version" or field == "osversion") and "os" in parsed:
            return self.__get_version_string(parsed["os"])
        elif (field == "browser_name" or field == "browsername") and "user_agent" in parsed and "family" in parsed["user_agent"]:
            return parsed["user_agent"]["family"]
        elif (field == "browser_version" or field == "browserversion") and "user_agent" in parsed:
            return self.__get_version_string(parsed["user_agent"])
        return None

    def __get_version_string(self, version):
        if version is None:
            return None
        major = version["major"] if "major" in version and version["major"] is not None else "0"
        minor = version["minor"] if "minor" in version and version["minor"] is not None else "0"
        patch = version["patch"] if "patch" in version and version["patch"] is not None else "0"
        return major + "." + minor + "." + patch

    def __compare_dates(self, first, second, compare):
        if first is None and second is None:
            return _ConfigEvaluation(False, False)

        first_date = self.__get_date(first)
        second_date = self.__get_date(second)
        if first_date is None or second_date is None:
            return _ConfigEvaluation(False, False)

        return _ConfigEvaluation(
            False,
            compare(first_date, second_date)
        )
    
    def __get_date(self, d):
        if d is None:
            return None
        
        epoch = int(d)
        if len(str(d)) >= 11:
            epoch /= 1000
            
        return datetime.fromtimestamp(epoch)
