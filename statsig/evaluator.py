import base64
import time
from datetime import datetime
import re
from hashlib import sha256
from struct import unpack
from ua_parser import user_agent_parser
from ip3country import CountryLookup


class _ConfigEvaluation:

    def __init__(self, fetch_from_server=False, boolean_value=False, json_value={}, rule_id="", secondary_exposures=[]):
        if fetch_from_server is None:
            fetch_from_server = False
        self.fetch_from_server = fetch_from_server
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
        self.secondary_exposures = secondary_exposures


class _Evaluator:
    def __init__(self):
        self._configs = dict()
        self._gates = dict()
        self._id_lists = dict()
        self._country_lookup = CountryLookup()

        self._gate_overrides = dict()
        self._config_overrides = dict()

    def setDownloadedConfigs(self, configs):
        new_gates = dict()
        for gate in configs.get("feature_gates", []):
            name = gate.get("name")
            if name is not None:
                new_gates[name] = gate

        new_configs = dict()
        for config in configs.get("dynamic_configs", []):
            name = config.get("name")
            if name is not None:
                new_configs[name] = config

        self._gates = new_gates
        self._configs = new_configs

        id_lists = configs.get("id_lists")
        if id_lists is not None:
            # Delete old id lists that no longer exists
            for list_name in self._id_lists.keys():
                if id_lists.get(list_name) is None and list_name in self._id_lists:
                    del self._id_lists[list_name]
            # Add new id lists
            for list_name in id_lists.keys():
                if self._id_lists.get(list_name) is None:
                    self._id_lists[list_name] = {"ids": {}, "time": 0}

    def getIDLists(self):
        return self._id_lists

    def override_gate(self, gate, value, user_id=None):
        gate_overrides = self._gate_overrides.get(gate)
        if gate_overrides is None:
            gate_overrides = dict()
        gate_overrides[user_id] = value
        self._gate_overrides[gate] = gate_overrides

    def override_config(self, config, value, user_id=None):
        config_overrides = self._config_overrides.get(config)
        if config_overrides is None:
            config_overrides = dict()
        config_overrides[user_id] = value
        self._config_overrides[config] = config_overrides

    def __lookup_gate_override(self, user, gate):
        gate_overrides = self._gate_overrides.get(gate)
        if gate_overrides is None:
            return None

        override = gate_overrides.get(user.user_id)
        if override is not None:
            return _ConfigEvaluation(boolean_value=override, rule_id="override")

        all_override = gate_overrides.get(None)
        if all_override is not None:
            return _ConfigEvaluation(boolean_value=all_override, rule_id="override")

        return None

    def __lookup_config_override(self, user, config):
        config_overrides = self._config_overrides.get(config)
        if config_overrides is None:
            return None

        override = config_overrides.get(user.user_id)
        if override is not None:
            return _ConfigEvaluation(json_value=override, rule_id="override")

        all_override = config_overrides.get(None)
        if all_override is not None:
            return _ConfigEvaluation(json_value=all_override, rule_id="override")
        return None

    def check_gate(self, user, gate):
        override = self.__lookup_gate_override(user, gate)
        if override is not None:
            return override
        eval_gate = self._gates.get(gate)
        if eval_gate is None:
            return _ConfigEvaluation()
        return self.__evaluate(user, eval_gate)

    def get_config(self, user, config):
        override = self.__lookup_config_override(user, config)
        if override is not None:
            return override
        eval_config = self._configs.get(config)
        if eval_config is None:
            return _ConfigEvaluation()

        return self.__evaluate(user, eval_config)

    def __check_id_in_list(self, id, list_name):
        list = self._id_lists.get(list_name)
        if list is None:
            return False
        ids = list.get("ids", dict())
        hashed = base64.b64encode(
            sha256(str(id).encode('utf-8')).digest()).decode('utf-8')[0:8]
        return ids.get(hashed) == True

    def get_all_gates(self):
        return self._gates

    def get_all_configs(self):
        return self._configs

    def __evaluate(self, user, config):
        exposures = []
        enabled = config.get("enabled", False)
        defaultValue = config.get("defaultValue", {})
        if not enabled:
            return _ConfigEvaluation(False, False, defaultValue, "disabled", exposures)

        for rule in config.get("rules", []):
            result = self.__evaluate_rule(user, rule)
            if result.fetch_from_server:
                return result
            if result.secondary_exposures is not None and len(result.secondary_exposures) > 0:
                exposures = exposures + result.secondary_exposures
            if result.boolean_value:
                user_passes = self.__eval_pass_percentage(user, rule, config)
                return_value = rule.get("returnValue", defaultValue)
                config = return_value if user_passes else defaultValue
                rule_id = rule.get("id", "")
                return _ConfigEvaluation(False, user_passes, config, rule_id, exposures)
        return _ConfigEvaluation(False, False, defaultValue, "default", exposures)

    def __evaluate_rule(self, user, rule):
        exposures = []
        eval_result = True
        for condition in rule.get("conditions", []):
            result = self.__evaluate_condition(user, condition)
            if result.fetch_from_server:
                return result
            if result.secondary_exposures is not None and len(result.secondary_exposures) > 0:
                exposures = exposures + result.secondary_exposures
            if not result.boolean_value:
                eval_result = False
        return_value = rule.get("return_value", {})
        rule_id = rule.get("id", "")
        return _ConfigEvaluation(False, eval_result, return_value, rule_id, exposures)

    def __evaluate_condition(self, user, condition):
        value = None

        type = condition.get("type", "").upper()
        target = condition.get("targetValue")
        field = condition.get("field", "")
        id_Type = condition.get("idType", "userID")
        if type == "PUBLIC":
            return _ConfigEvaluation(False, True)
        elif type == "FAIL_GATE" or type == "PASS_GATE":
            other_result = self.check_gate(user, target)
            if (other_result.fetch_from_server):
                return _ConfigEvaluation(True)
            new_exposure = {
                "gate": target,
                "gateValue": "true" if other_result.boolean_value else "false",
                "ruleID": other_result.rule_id
            }
            exposures = [new_exposure]
            if other_result.secondary_exposures is not None and len(other_result.secondary_exposures) > 0:
                exposures = other_result.secondary_exposures + exposures
            pass_gate = other_result.boolean_value if type == "PASS_GATE" else not other_result.boolean_value
            return _ConfigEvaluation(other_result.fetch_from_server, pass_gate, {}, None, exposures)
        elif type == "IP_BASED":
            value = self.__get_from_user(user, field)
            if value is None:
                ip = self.__get_from_user(user, "ip")
                if ip is not None and field == "country":
                    value = self._country_lookup.lookupStr(ip)
            if value is None:
                return _ConfigEvaluation(False, False)
        elif type == "UA_BASED":
            value = self.__get_from_user_agent(user, field)
        elif type == "USER_FIELD":
            value = self.__get_from_user(user, field)
        elif type == "CURRENT_TIME":
            value = round(time.time() * 1000)
        elif type == "ENVIRONMENT_FIELD":
            value = self.__get_from_environment(user, field)
        elif type == "USER_BUCKET":
            salt = condition.get("additionalValues", {
                                 "salt": None}).get("salt")
            salt_str = self.__get_value_as_string(salt)
            unit_id = self.__get_unit_id(user, id_Type) or ""
            value = int(self.__compute_user_hash(
                salt_str + "." + unit_id) % 1000)
        elif type == "UNIT_ID":
            value = self.__get_unit_id(user, id_Type)
        else:
            return _ConfigEvaluation(True)

        op = condition.get("operator")
        if op == "gt":
            val = self.__get_value_as_float(value)
            target = self.__get_value_as_float(target)
            if val is None or target is None:
                return _ConfigEvaluation(False, False)
            return _ConfigEvaluation(False, val > target)
        elif op == "gte":
            val = self.__get_value_as_float(value)
            target = self.__get_value_as_float(target)
            if val is None or target is None:
                return _ConfigEvaluation(False, False)
            return _ConfigEvaluation(False, val >= target)
        elif op == "lt":
            val = self.__get_value_as_float(value)
            target = self.__get_value_as_float(target)
            if val is None or target is None:
                return _ConfigEvaluation(False, False)
            return _ConfigEvaluation(False, val < target)
        elif op == "lte":
            val = self.__get_value_as_float(value)
            target = self.__get_value_as_float(target)
            if val is None or target is None:
                return _ConfigEvaluation(False, False)
            return _ConfigEvaluation(False, val <= target)
        elif op == "version_gt":
            res = self.__version_compare_helper(
                value, target, lambda a, b: self.__version_compare(a, b) > 0)
            return _ConfigEvaluation(False, res)
        elif op == "version_gte":
            res = self.__version_compare_helper(
                value, target, lambda a, b: self.__version_compare(a, b) >= 0)
            return _ConfigEvaluation(False, res)
        elif op == "version_lt":
            res = self.__version_compare_helper(
                value, target, lambda a, b: self.__version_compare(a, b) < 0)
            return _ConfigEvaluation(False, res)
        elif op == "version_lte":
            res = self.__version_compare_helper(
                value, target, lambda a, b: self.__version_compare(a, b) <= 0)
            return _ConfigEvaluation(False, res)
        elif op == "version_eq":
            res = self.__version_compare_helper(
                value, target, lambda a, b: self.__version_compare(a, b) == 0)
            return _ConfigEvaluation(False, res)
        elif op == "version_neq":
            res = self.__version_compare_helper(
                value, target, lambda a, b: self.__version_compare(a, b) != 0)
            return _ConfigEvaluation(False, res)
        elif op == "any":
            return _ConfigEvaluation(False, self.__match_string_in_array(value, target, lambda a, b: a.upper().lower() == b.upper().lower()))
        elif op == "none":
            return _ConfigEvaluation(False, not self.__match_string_in_array(value, target, lambda a, b: a.upper().lower() == b.upper().lower()))
        elif op == "any_case_sensitive":
            return _ConfigEvaluation(False, self.__match_string_in_array(value, target, lambda a, b: a == b))
        elif op == "none_case_sensitive":
            return _ConfigEvaluation(False, not self.__match_string_in_array(value, target, lambda a, b: a == b))
        elif op == "str_starts_with_any":
            return _ConfigEvaluation(False, self.__match_string_in_array(value, target, lambda a, b: a.upper().lower().startswith(b.upper().lower())))
        elif op == "str_ends_with_any":
            return _ConfigEvaluation(False, self.__match_string_in_array(value, target, lambda a, b: a.upper().lower().endswith(b.upper().lower())))
        elif op == "str_contains_any":
            return _ConfigEvaluation(False, self.__match_string_in_array(value, target, lambda a, b: b.upper().lower() in a.upper().lower()))
        elif op == "str_contains_none":
            return _ConfigEvaluation(False, not self.__match_string_in_array(value, target, lambda a, b: b.upper().lower() in a.upper().lower()))
        elif op == "str_matches":
            str_value = self.__get_value_as_string(value)
            str_target = self.__get_value_as_string(target)
            if str_value == None or str_target == None:
                return _ConfigEvaluation(False, False)
            return _ConfigEvaluation(False, bool(re.match(str_target, str_value)))
        elif op == "eq":
            return _ConfigEvaluation(False, value == target)
        elif op == "neq":
            return _ConfigEvaluation(False, value != target)
        elif op == "before":
            return self.__compare_dates(value, target, lambda a, b: a.date() < b.date())
        elif op == "after":
            return self.__compare_dates(value, target, lambda a, b: a.date() > b.date())
        elif op == "on":
            return self.__compare_dates(value, target, lambda a, b: a.date() == b.date())
        elif op == "in_segment_list" or op == "not_in_segment_list":
            in_list = self.__check_id_in_list(value, target)
            return _ConfigEvaluation(False, in_list if op == "in_segment_list" else not in_list)

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
        rule_salt = rule.get("salt", rule.get("id", ""))
        id = self.__get_unit_id(user, rule.get("idType", "userID")) or ""
        config_salt = config.get("salt", "")
        hash = self.__compute_user_hash(
            config_salt + "." + rule_salt + "." + id
        )
        pass_percentage = rule.get("passPercentage", 0)
        return (hash % 10000) < pass_percentage * 100

    def __get_unit_id(self, user, id_type):
        if id_type is not None and id_type.lower() != "userid":
            if user.custom_ids is None:
                return None
            return user.custom_ids.get(id_type, None) or user.custom_ids.get(id_type.lower(), None)
        return user.user_id

    def __match_string_in_array(self, value, target, compare):
        str_value = self.__get_value_as_string(value)
        if str_value is None or target is None:
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
        if field == "osname" or field == "os_name":
            return parsed.get("os", {"family": None}).get("family")
        elif field == "os_version" or field == "osversion":
            return self.__get_version_string(parsed.get("os"))
        elif (field == "browser_name" or field == "browsername"):
            return parsed.get("user_agent", {"family": None}).get("family")
        elif (field == "browser_version" or field == "browserversion"):
            return self.__get_version_string(parsed.get("user_agent"))
        return None

    def __get_version_string(self, version):
        if version is None:
            return None
        major = version.get("major", "0")
        if major is None:
            major = "0"
        minor = version.get("minor", "0")
        if minor is None:
            minor = "0"
        patch = version.get("patch", "0")
        if patch is None:
            patch = "0"
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
