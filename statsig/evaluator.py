import base64
import time
from datetime import datetime
import re
from hashlib import sha256
from struct import unpack
from typing import Dict

from ua_parser import user_agent_parser
from ip3country import CountryLookup

from .statsig_user import StatsigUser
from .client_initialize_formatter import ClientInitializeResponseFormatter
from .evaluation_details import EvaluationDetails, EvaluationReason
from .spec_store import _SpecStore
from .config_evaluation import _ConfigEvaluation
from .utils import HashingAlgorithm


class _Evaluator:
    def __init__(self, spec_store: _SpecStore):
        self._spec_store = spec_store

        self._country_lookup = CountryLookup()
        self._gate_overrides: Dict[str, dict] = {}
        self._config_overrides: Dict[str, dict] = {}
        self._layer_overrides: Dict[str, dict] = {}

    def override_gate(self, gate, value, user_id=None):
        gate_overrides = self._gate_overrides.get(gate)
        if gate_overrides is None:
            gate_overrides = {}
        gate_overrides[user_id] = value
        self._gate_overrides[gate] = gate_overrides

    def override_config(self, config, value, user_id=None):
        config_overrides = self._config_overrides.get(config)
        if config_overrides is None:
            config_overrides = {}
        config_overrides[user_id] = value
        self._config_overrides[config] = config_overrides

    def override_layer(self, layer, value, user_id=None):
        layer_overrides = self._layer_overrides.get(layer)
        if layer_overrides is None:
            layer_overrides = {}
        layer_overrides[user_id] = value
        self._layer_overrides[layer] = layer_overrides

    def remove_gate_override(self, gate, user_id=None):
        gate_overrides = self._gate_overrides.get(gate)
        if gate_overrides is None:
            return
        if user_id in gate_overrides:
            del gate_overrides[user_id]
        self._gate_overrides[gate] = gate_overrides

    def remove_config_override(self, config, user_id=None):
        config_overrides = self._config_overrides.get(config)
        if config_overrides is None:
            return
        if user_id in config_overrides:
            del config_overrides[user_id]
        self._config_overrides[config] = config_overrides

    def remove_layer_override(self, layer, user_id=None):
        layer_overrides = self._layer_overrides.get(layer)
        if layer_overrides is None:
            return
        if user_id in layer_overrides:
            del layer_overrides[user_id]
        self._layer_overrides[layer] = layer_overrides

    def remove_all_overrides(self):
        self._gate_overrides = {}
        self._config_overrides = {}
        self._layer_overrides = {}

    def clean_exposures(self, exposures):
        seen: Dict[str, bool] = {}
        result = []
        for exposure in exposures:
            if exposure['gate'].startswith('segment:'):
                continue
            key = f"{exposure['gate']}|{exposure['gateValue']}|{exposure['ruleID']}"
            if not seen.get(key, False):
                seen[key] = True
                result.append(exposure)
        return result

    def get_client_initialize_response(
            self,
            user: StatsigUser,
            hash: HashingAlgorithm,
            client_sdk_key=None,
            include_local_override=False,
    ):
        if not self._spec_store.is_ready_for_checks():
            return None

        if self._spec_store.last_update_time == 0:
            return None

        return ClientInitializeResponseFormatter \
            .get_formatted_response(self.__eval_config, user, self._spec_store, self, hash, client_sdk_key,
                                    include_local_override)

    def _create_evaluation_details(self, reason: EvaluationReason):
        if reason == EvaluationReason.uninitialized:
            return EvaluationDetails(0, 0, reason)

        return EvaluationDetails(
            self._spec_store.last_update_time, self._spec_store.initial_update_time, reason)

    def __lookup_gate_override(self, user, gate):
        gate_overrides = self._gate_overrides.get(gate)
        if gate_overrides is None:
            return None

        eval_details = self._create_evaluation_details(
            EvaluationReason.local_override)
        override = self.__lookup_override(gate_overrides, user)
        if override is not None:
            return _ConfigEvaluation(boolean_value=override, rule_id="override",
                                     evaluation_details=eval_details)

        all_override = gate_overrides.get(None)
        if all_override is not None:
            return _ConfigEvaluation(
                boolean_value=all_override, rule_id="override", evaluation_details=eval_details)

        return None

    def lookup_gate_override(self, user, gate):
        return self.__lookup_gate_override(user, gate)

    def __lookup_config_override(self, user, config):
        config_overrides = self._config_overrides.get(config)
        if config_overrides is None:
            return None

        eval_details = self._create_evaluation_details(
            EvaluationReason.local_override)
        override = self.__lookup_override(config_overrides, user)
        if override is not None:
            return _ConfigEvaluation(json_value=override, rule_id="override",
                                     evaluation_details=eval_details)

        all_override = config_overrides.get(None)
        if all_override is not None:
            return _ConfigEvaluation(
                json_value=all_override, rule_id="override", evaluation_details=eval_details)
        return None

    def lookup_config_override(self, user, config):
        return self.__lookup_config_override(user, config)

    def __lookup_layer_override(self, user, config):
        layer_overrides = self._layer_overrides.get(config)
        if layer_overrides is None:
            return None

        eval_details = self._create_evaluation_details(
            EvaluationReason.local_override)
        override = self.__lookup_override(layer_overrides, user)
        if override is not None:
            return _ConfigEvaluation(json_value=override, rule_id="override",
                                     evaluation_details=eval_details)

        all_override = layer_overrides.get(None)
        if all_override is not None:
            return _ConfigEvaluation(
                json_value=all_override, rule_id="override", evaluation_details=eval_details)
        return None

    def __lookup_override(self, config_overrides, user):
        override = config_overrides.get(user.user_id)
        if override is None and user.custom_ids is not None:
            for id_name in user.custom_ids:
                override = config_overrides.get(user.custom_ids[id_name])
                if override is not None:
                    break
        return override

    def unsupported_or_unrecognized(self, config_name):
        if config_name in self._spec_store.unsupported_configs:
            return _ConfigEvaluation(
                evaluation_details=self._create_evaluation_details(
                    EvaluationReason.unsupported))
        return _ConfigEvaluation(
            evaluation_details=self._create_evaluation_details(
                EvaluationReason.unrecognized))

    def check_gate(self, user, gate, end_result=None, is_nested=False):
        override = self.__lookup_gate_override(user, gate)
        if override is not None:
            return override

        if self._spec_store.init_reason == EvaluationReason.uninitialized:
            return _ConfigEvaluation(
                evaluation_details=self._create_evaluation_details(
                    EvaluationReason.uninitialized))
        eval_gate = self._spec_store.get_gate(gate)
        if eval_gate is None:
            return self.unsupported_or_unrecognized(gate)
        if end_result is None:
            end_result = _ConfigEvaluation()
        self.__eval_config(user, eval_gate, end_result, is_nested)
        return end_result

    def get_config(self, user, config):
        override = self.__lookup_config_override(user, config)
        if override is not None:
            return override

        if self._spec_store.init_reason == EvaluationReason.uninitialized:
            return _ConfigEvaluation(
                evaluation_details=self._create_evaluation_details(
                    EvaluationReason.uninitialized))

        eval_config = self._spec_store.get_config(config)
        if eval_config is None:
            return self.unsupported_or_unrecognized(config)
        result = _ConfigEvaluation()
        self.__eval_config(user, eval_config, result)
        return result

    def get_layer(self, user, layer):
        override = self.__lookup_layer_override(user, layer)
        if override is not None:
            return override

        if self._spec_store.init_reason == EvaluationReason.uninitialized:
            return _ConfigEvaluation(
                evaluation_details=self._create_evaluation_details(
                    EvaluationReason.uninitialized))

        eval_layer = self._spec_store.get_layer(layer)
        if eval_layer is None:
            return self.unsupported_or_unrecognized(layer)
        result = _ConfigEvaluation()
        self.__eval_config(user, eval_layer, result)
        return result

    def __eval_config(self, user, config, end_result, is_nested=False):
        if config is None:
            end_result.evaluation_details = self._create_evaluation_details(
                EvaluationReason.unrecognized)
            return
        try:
            self.__evaluate(user, config, end_result, is_nested)
            end_result.evaluation_details = self._create_evaluation_details(
                self._spec_store.init_reason)
        except RecursionError:
            raise
        except Exception:
            end_result.evaluation_details = self._create_evaluation_details(
                EvaluationReason.error)
            end_result.rule_id = "error"

    def __check_id_in_list(self, id, list_name):
        curr_list = self._spec_store.get_id_list(list_name)
        if curr_list is None:
            return False
        ids = curr_list.get("ids", set())
        hashed = base64.b64encode(
            sha256(str(id).encode('utf-8')).digest()).decode('utf-8')[0:8]
        return hashed in ids

    def __evaluate(self, user, config, end_result, is_nested=False):
        if not config.get("enabled", False):
            self.__finalize_eval_result(config, end_result, False, None, is_nested)
            return

        for rule in config.get("rules", []):
            self.__evaluate_rule(user, rule, end_result)
            if end_result.boolean_value:
                if self.__evaluate_delegate(user, rule, end_result) is not None:
                    self.__finalize_exposures(end_result)
                    return

                user_passes = self.__eval_pass_percentage(user, rule, config)
                self.__finalize_eval_result(config, end_result, user_passes, rule, is_nested)
                return

        self.__finalize_eval_result(config, end_result, False, None, is_nested)

    def __finalize_eval_result(self, config, end_result, did_pass, rule, is_nested=False):
        end_result.boolean_value = did_pass

        if rule is None:
            end_result.json_value = config.get("defaultValue", {})
            end_result.group_name = None
            end_result.is_experiment_group = False
            end_result.rule_id = "default" if config.get("enabled") else "disabled"
        else:
            end_result.json_value = rule.get("returnValue") if did_pass else config.get("defaultValue", {})
            end_result.group_name = rule.get("groupName", None)
            end_result.is_experiment_group = rule.get("isExperimentGroup", False)
            end_result.rule_id = rule.get("id", "")

        if not is_nested:
            self.__finalize_exposures(end_result)

    def __finalize_exposures(self, end_result):
        end_result.secondary_exposures = self.clean_exposures(end_result.secondary_exposures)
        end_result.undelegated_secondary_exposures = self.clean_exposures(end_result.undelegated_secondary_exposures)

    def __evaluate_rule(self, user, rule, end_result):
        total_eval_result = True
        for condition in rule.get("conditions", []):
            eval_result = self.__evaluate_condition(user, condition, end_result)
            if not eval_result:
                total_eval_result = False
        end_result.boolean_value = total_eval_result

    def __evaluate_delegate(self, user, rule, end_result):
        config_delegate = rule.get("configDelegate", None)
        if config_delegate is None:
            return None

        config = self._spec_store.get_config(config_delegate)
        if config is None:
            return None

        end_result.undelegated_secondary_exposures = end_result.secondary_exposures[:]

        self.__evaluate(user, config, end_result, True)
        end_result.explicit_parameters = config.get(
            "explicitParameters", [])
        end_result.allocated_experiment = config_delegate
        return end_result

    def __evaluate_condition(self, user, condition, end_result):
        value = None
        type = condition.get("type", "").upper()
        target = condition.get("targetValue")
        field = condition.get("field", "")
        id_Type = condition.get("idType", "userID")
        if type == "PUBLIC":
            return True
        if type in ("FAIL_GATE", "PASS_GATE"):
            self.check_gate(user, target, end_result, True)

            new_exposure = {
                "gate": target,
                "gateValue": "true" if end_result.boolean_value else "false",
                "ruleID": end_result.rule_id
            }

            end_result.secondary_exposures.append(new_exposure)

            pass_gate = end_result.boolean_value if type == "PASS_GATE" else not end_result.boolean_value
            return pass_gate
        if type in ("MULTI_PASS_GATE", "MULTI_FAIL_GATE"):
            if target is None or len(target) == 0:
                return False
            pass_gate = False
            for gate in target:
                other_result = self.check_gate(user, gate)

                new_exposure = {
                    "gate": gate,
                    "gateValue": "true" if other_result.boolean_value else "false",
                    "ruleID": other_result.rule_id
                }
                end_result.secondary_exposures.append(new_exposure)

                pass_gate = pass_gate or other_result.boolean_value if type == "MULTI_PASS_GATE" else pass_gate or not other_result.boolean_value
                if pass_gate:
                    break
            return pass_gate
        if type == "IP_BASED":
            value = self.__get_from_user(user, field)
            if value is None:
                ip = self.__get_from_user(user, "ip")
                if ip is not None and field == "country":
                    value = self._country_lookup.lookupStr(ip)
            if value is None:
                return False
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
            salt_str = self.__get_value_as_string(salt) or ""
            unit_id = self.__get_unit_id(user, id_Type) or ""
            value = int(self.__compute_user_hash(
                salt_str + "." + unit_id) % 1000)
        elif type == "UNIT_ID":
            value = self.__get_unit_id(user, id_Type)

        op = condition.get("operator")
        user_bucket = condition.get("user_bucket")
        if op == "gt":
            val = self.__get_value_as_float(value)
            target = self.__get_value_as_float(target)
            if val is None or target is None:
                return False
            return val > target
        if op == "gte":
            val = self.__get_value_as_float(value)
            target = self.__get_value_as_float(target)
            if val is None or target is None:
                return False
            return val >= target
        if op == "lt":
            val = self.__get_value_as_float(value)
            target = self.__get_value_as_float(target)
            if val is None or target is None:
                return False
            return val < target
        if op == "lte":
            val = self.__get_value_as_float(value)
            target = self.__get_value_as_float(target)
            if val is None or target is None:
                return False
            return val <= target
        if op == "version_gt":
            return self.__version_compare_helper(
                value, target, lambda result: result > 0)
        if op == "version_gte":
            return self.__version_compare_helper(
                value, target, lambda result: result >= 0)
        if op == "version_lt":
            return self.__version_compare_helper(
                value, target, lambda result: result < 0)
        if op == "version_lte":
            return self.__version_compare_helper(
                value, target, lambda result: result <= 0)
        if op == "version_eq":
            return self.__version_compare_helper(
                value, target, lambda result: result == 0)
        if op == "version_neq":
            return self.__version_compare_helper(
                value, target, lambda result: result != 0)
        if op == "any":
            if user_bucket is not None:
                return self.__lookup_user_bucket(value, user_bucket)
            return self.__match_string_in_array(
                value, target, lambda a, b: a.upper().lower() == b.upper().lower())
        if op == "none":
            if user_bucket is not None:
                return not self.__lookup_user_bucket(value, user_bucket)
            return not self.__match_string_in_array(
                value, target, lambda a, b: a.upper().lower() == b.upper().lower())
        if op == "any_case_sensitive":
            return self.__match_string_in_array(
                value, target, lambda a, b: a == b)
        if op == "none_case_sensitive":
            return not self.__match_string_in_array(
                value, target, lambda a, b: a == b)
        if op == "str_starts_with_any":
            return self.__match_string_in_array(
                value, target, lambda a, b: a.upper().lower().startswith(
                    b.upper().lower()))
        if op == "str_ends_with_any":
            return self.__match_string_in_array(
                value, target, lambda a, b: a.upper().lower().endswith(
                    b.upper().lower()))
        if op == "str_contains_any":
            return self.__match_string_in_array(
                value, target, lambda a, b: b.upper().lower() in a.upper().lower())
        if op == "str_contains_none":
            return not self.__match_string_in_array(
                value, target, lambda a, b: b.upper().lower() in a.upper().lower())
        if op == "str_matches":
            str_value = self.__get_value_as_string(value)
            str_target = self.__get_value_as_string(target)
            if str_value is None or str_target is None:
                return False
            return bool(
                re.search(str_target, str_value))
        if op == "eq":
            return value == target
        if op == "neq":
            return value != target
        if op == "before":
            return self.__compare_dates(value, target, lambda a, b: a < b)
        if op == "after":
            return self.__compare_dates(value, target, lambda a, b: a > b)
        if op == "on":
            return self.__compare_dates(
                value, target, lambda a, b: a.date() == b.date())
        if op in ("in_segment_list", "not_in_segment_list"):
            in_list = self.__check_id_in_list(value, target)
            return in_list if op == "in_segment_list" else not in_list

        return True

    def __get_from_user(self, user, field):
        value = None
        lower_field = field.lower()
        if lower_field in ("userid", "user_id"):
            value = user.user_id
        elif lower_field == "email":
            value = user.email
        elif lower_field in ("ip", "ipaddress", "ip_address"):
            value = user.ip
        elif lower_field in ("useragent", "user_agent"):
            value = user.user_agent
        elif lower_field == "country":
            value = user.country
        elif lower_field == "locale":
            value = user.locale
        elif lower_field in ("appversion", "app_version"):
            value = user.app_version

        if (value is None or value == "") and user.custom is not None:
            if field in user.custom:
                value = user.custom[field]
            elif field.upper().lower() in user.custom:
                value = user.custom[field.upper().lower()]

        if (value is None or value == "") and user.private_attributes is not None:
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
        if field.lower() in user._statsig_environment:
            return user._statsig_environment[field]
        return None

    def __compute_user_hash(self, input):
        return unpack('>Q', sha256(str(input).encode('utf-8')).digest()[:8])[0]

    def __eval_pass_percentage(self, user, rule, config):
        rule_salt = rule.get("salt", rule.get("id", ""))
        id = self.__get_unit_id(user, rule.get("idType", "userID")) or ""
        config_salt = config.get("salt", "")
        hash = self.__compute_user_hash(
            config_salt + "." + rule_salt + "." + str(id)
        )
        pass_percentage = rule.get("passPercentage", 0)
        return (hash % 10000) < pass_percentage * 100

    def __get_unit_id(self, user, id_type):
        if id_type is not None and id_type.lower() != "userid":
            if user.custom_ids is None:
                return None
            custom_id = user.custom_ids.get(
                id_type, None)
            if custom_id is not None:
                return custom_id
            return user.custom_ids.get(id_type.lower(), None)
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

    def __lookup_user_bucket(self, val, lookup):
        if isinstance(val, int):
            return val in lookup
        return False

    def __version_compare(self, v1, v2, compare):
        p1 = v1.split(".")
        p2 = v2.split(".")

        i = 0
        try:
            while i < max(len(p1), len(p2)):
                c1 = 0
                c2 = 0
                if i < len(p1):
                    c1 = int(float(p1[i]))
                if i < len(p2):
                    c2 = int(float(p2[i]))
                if c1 < c2:
                    return compare(-1)
                if c1 > c2:
                    return compare(1)
                i += 1
        except ValueError:
            return False

        return compare(0)

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

        return self.__version_compare(v1_str, v2_str, compare)

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
        if field in ("osname", "os_name"):
            return parsed.get("os", {"family": None}).get("family")
        if field in ("os_version", "osversion"):
            return self.__get_version_string(parsed.get("os"))
        if field in ("browser_name", "browsername"):
            return parsed.get("user_agent", {"family": None}).get("family")
        if field in ("browser_version", "browserversion"):
            return self.__get_version_string(parsed.get("user_agent"))
        return None

    def __get_version_string(self, version):
        if version is None:
            return None

        major = self.__get_numeric_subver(version, "major")
        if major is None:
            return None
        minor = self.__get_numeric_subver(version, "minor")
        if minor is None:
            return None
        patch = self.__get_numeric_subver(version, "patch")
        if patch is None:
            return None
        return str.format("{}.{}.{}", major, minor, patch)

    def __get_numeric_subver(self, version, subver):
        ver = version.get(subver, "0")
        if ver is None:
            return 0
        try:
            numeric = int(ver)
            return numeric
        except ValueError:
            return None

    def __compare_dates(self, first, second, compare):
        if first is None and second is None:
            return False

        first_date = self.__get_date(first)
        second_date = self.__get_date(second)
        if first_date is None or second_date is None:
            return False

        return compare(first_date, second_date)

    def __get_date(self, d):
        if d is None:
            return None

        epoch = int(d)
        if len(str(d)) >= 11:
            epoch //= 1000

        return datetime.fromtimestamp(epoch)
