import base64
import re
import time
from datetime import datetime
from hashlib import sha256
from typing import Any, Dict, Optional, Union

from ip3country import CountryLookup

from .client_initialize_formatter import ClientInitializeResponseFormatter
from .config_evaluation import _ConfigEvaluation
from .evaluation_context import EvaluationContext
from .evaluation_details import EvaluationDetails, EvaluationReason, DataSource
from .globals import logger
from .spec_store import _SpecStore, EntityType
from .statsig_user import StatsigUser
from .utils import HashingAlgorithm, JSONValue, sha256_hash


def load_ua_parser():
    try:
        from ua_parser import user_agent_parser  # pylint: disable=import-outside-toplevel
        return user_agent_parser
    except ImportError:
        logger.warning("ua_parser module not available")
        return None


class _Evaluator:
    def __init__(self, spec_store: _SpecStore, global_custom_fields: Optional[Dict[str, JSONValue]],
                 disable_ua_parser: bool = False, disable_country_lookup: bool = False):
        self._spec_store = spec_store
        self._global_custom_fields = global_custom_fields
        self._disable_ua_parser = disable_ua_parser
        self._disable_country_lookup = disable_country_lookup

        self._country_lookup: Optional[CountryLookup] = None
        self._ua_parser: Optional[Any] = None  # Will be the ua_parser.user_agent_parser module
        self._gate_overrides: Dict[str, dict] = {}
        self._config_overrides: Dict[str, dict] = {}
        self._layer_overrides: Dict[str, dict] = {}

    def initialize(self):
        if not self._disable_country_lookup:
            self._country_lookup = CountryLookup()
        if not self._disable_ua_parser:
            self._ua_parser = load_ua_parser()

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
            target_app_id: Optional[str] = None,
    ):
        if not self._spec_store.is_ready_for_checks():
            return None

        if self._spec_store.last_update_time() == 0:
            return None

        return ClientInitializeResponseFormatter \
            .get_formatted_response(self.__eval_config, user, self._spec_store, self, hash, client_sdk_key,
                                    include_local_override, target_app_id)

    def _create_evaluation_details(self,
                                   reason: EvaluationReason = EvaluationReason.none,
                                   source: Optional[DataSource] = None):
        if source is None:
            source = self._spec_store.init_source
        if source == DataSource.UNINITIALIZED:
            return EvaluationDetails(0, 0, source, reason)

        return EvaluationDetails(
            self._spec_store.last_update_time(), self._spec_store.initial_update_time, source, reason)


    def _update_evaluation_details_if_needed(self, end_result: _ConfigEvaluation) -> None:
        current_details = end_result.evaluation_details

        if current_details is None:
            end_result.evaluation_details = self._create_evaluation_details()
            return

        if current_details.source in [DataSource.UA_NOT_LOADED, DataSource.COUNTRY_NOT_LOADED]:
            return

        end_result.evaluation_details = self._create_evaluation_details()

    def __lookup_gate_override(self, user, gate):
        gate_overrides = self._gate_overrides.get(gate)
        if gate_overrides is None:
            return None

        eval_details = self._create_evaluation_details(EvaluationReason.local_override)
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

        eval_details = self._create_evaluation_details(EvaluationReason.local_override)
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

        eval_details = self._create_evaluation_details(EvaluationReason.local_override)
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

    def __lookup_config_mapping(self, user: StatsigUser, config_name: str, spec_type: EntityType,
                                end_result: _ConfigEvaluation,
                                context: EvaluationContext,
                                maybe_config: Union[Dict[str, Any], None] = None,) -> bool:
        overrides = self._spec_store.get_overrides()
        if overrides is None or not isinstance(overrides, dict):
            return False

        override_rules = self._spec_store.get_override_rules()
        if override_rules is None or not isinstance(override_rules, dict):
            return False

        mapping_list = overrides.get(config_name, None)
        if mapping_list is None or not isinstance(mapping_list, list):
            return False

        spec_salt = ""
        if maybe_config is not None:
            spec_salt = maybe_config.get("salt", "")

        for mapping in mapping_list:
            for override_rule in mapping.get("rules", []):
                start_time = override_rule.get("start_time", 0)
                if start_time > int(time.time() * 1000):
                    continue

                rule = override_rules.get(override_rule.get("rule_name"), None)
                if rule is None:
                    continue

                end_result.reset()
                context.sampling_rate = rule.get("samplingRate", None)
                self.__evaluate_rule(user, rule, end_result, context)
                if not end_result.boolean_value or end_result.evaluation_details.reason in (
                        EvaluationReason.unsupported, EvaluationReason.unrecognized):
                    end_result.reset()
                    continue
                end_result.reset()
                override_config_name = mapping.get("new_config_name", None)
                new_config = self.__get_config_by_entity_type(override_config_name, spec_type)

                config_pass = self.__eval_pass_percentage(user, rule, new_config, spec_salt)
                if config_pass:
                    end_result.override_config_name = override_config_name
                    self.__evaluate(user, override_config_name, spec_type, end_result, context)
                    if end_result.evaluation_details.reason == EvaluationReason.none:
                        return True
        return False

    def __get_config_by_entity_type(self, entity_name: str, entity_type: EntityType):
        if entity_type == EntityType.GATE:
            return self._spec_store.get_gate(entity_name)
        if entity_type == EntityType.CONFIG:
            return self._spec_store.get_config(entity_name)
        if entity_type == EntityType.LAYER:
            return self._spec_store.get_layer(entity_name)

        return None

    def unsupported_or_unrecognized(self, config_name, end_result):
        end_result.reset()
        if config_name in self._spec_store.unsupported_configs:
            return self._create_evaluation_details(EvaluationReason.unsupported)
        return self._create_evaluation_details(EvaluationReason.unrecognized)

    def check_gate(self, user, gate, end_result=None, is_nested=False, context: Optional[EvaluationContext] = None):
        override = self.__lookup_gate_override(user, gate)
        if override is not None:
            return override

        if end_result is None:
            end_result = _ConfigEvaluation()
        if context is None:
            context = EvaluationContext()
        self.__eval_config(user, gate, EntityType.GATE, end_result, context, is_nested)
        return end_result

    def get_config(self, user, config_name):
        override = self.__lookup_config_override(user, config_name)
        if override is not None:
            return override

        result = _ConfigEvaluation()
        self.__eval_config(user, config_name, EntityType.CONFIG, result, EvaluationContext())
        return result

    def get_layer(self, user, layer_name):
        override = self.__lookup_layer_override(user, layer_name)
        if override is not None:
            return override

        result = _ConfigEvaluation()
        self.__eval_config(user, layer_name, EntityType.LAYER, result, EvaluationContext())
        return result

    def __eval_config(self, user, config_name, entity_type: EntityType, end_result, context: EvaluationContext, is_nested=False):
        try:
            if not entity_type:
                logger.warning("invalid entity type in evaluation: %s", config_name)
                end_result.rule_id = "error"
                return
            self.__evaluate(user, config_name, entity_type, end_result, context, is_nested)
        except RecursionError:
            raise
        except Exception:
            end_result.evaluation_details = self._create_evaluation_details(EvaluationReason.error)
            end_result.rule_id = "error"

    def __check_id_in_list(self, id, list_name):
        curr_list = self._spec_store.get_id_list(list_name)
        if curr_list is None:
            return False
        ids = curr_list.get("ids", set())
        hashed = base64.b64encode(
            sha256(str(id).encode('utf-8')).digest()).decode('utf-8')[0:8]
        return hashed in ids

    def __evaluate(self, user, config_name, entity_type, end_result, context: EvaluationContext, is_nested=False):
        maybe_config_spec = self.__get_config_by_entity_type(config_name, entity_type)

        override_config = self.__lookup_config_mapping(user, config_name, entity_type, end_result, context, maybe_config_spec)
        if override_config:
            return

        if maybe_config_spec is None:
            end_result.evaluation_details = self.unsupported_or_unrecognized(config_name, end_result)
            return

        if not maybe_config_spec.get("enabled", False):
            self.__finalize_eval_result(maybe_config_spec, end_result, False, None, is_nested)
            return

        for rule in maybe_config_spec.get("rules", []):
            context.sampling_rate = rule.get("samplingRate", None)
            self.__evaluate_rule(user, rule, end_result, context)
            if end_result.boolean_value:
                if self.__evaluate_delegate(user, rule, end_result, context) is not None:
                    self.__finalize_exposures(end_result)
                    return

                user_passes = self.__eval_pass_percentage(user, rule, maybe_config_spec)
                self.__finalize_eval_result(maybe_config_spec, end_result, user_passes, rule, is_nested)
                return

        self.__finalize_eval_result(maybe_config_spec, end_result, False, None, is_nested)

    def __finalize_eval_result(self, config, end_result, did_pass, rule, is_nested=False):
        end_result.boolean_value = did_pass
        end_result.id_type = config.get("idType", "")
        if config.get("forwardAllExposures", False):
            end_result.forward_all_exposures = True
        if config.get("version", None) is not None:
            end_result.version = config.get("version")

        if end_result.evaluation_details is not None and end_result.evaluation_details.source not in (
        DataSource.UA_NOT_LOADED, DataSource.COUNTRY_NOT_LOADED):
            end_result.evaluation_details = self._create_evaluation_details()

        self._update_evaluation_details_if_needed(end_result)

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
            end_result.sample_rate = rule.get("samplingRate", None)

        if not is_nested:
            self.__finalize_exposures(end_result)

    def __finalize_exposures(self, end_result):
        end_result.secondary_exposures = self.clean_exposures(end_result.secondary_exposures)
        end_result.undelegated_secondary_exposures = self.clean_exposures(end_result.undelegated_secondary_exposures)

    def __evaluate_rule(self, user, rule, end_result, context: EvaluationContext):
        total_eval_result = True
        for condition in rule.get("conditions", []):
            eval_result = self.__evaluate_condition(user, condition, end_result, context)
            if not eval_result:
                total_eval_result = False
        end_result.boolean_value = total_eval_result

    def __evaluate_delegate(self, user, rule, end_result, context: EvaluationContext):
        config_delegate = rule.get("configDelegate", None)
        if config_delegate is None:
            return None

        config = self._spec_store.get_config(config_delegate)
        if config is None:
            return None

        end_result.undelegated_secondary_exposures = end_result.secondary_exposures[:]

        self.__evaluate(user, config_delegate, EntityType.CONFIG, end_result, context, True)
        end_result.explicit_parameters = config.get(
            "explicitParameters", [])
        end_result.allocated_experiment = config_delegate
        return end_result

    def __evaluate_condition(self, user, condition, end_result, context: EvaluationContext):
        value = None
        type = condition.get("type", "").upper()
        target = condition.get("targetValue")
        field = condition.get("field", "")
        id_Type = condition.get("idType", "userID")
        if type == "PUBLIC":
            end_result.analytical_condition = context.sampling_rate is None
            return True
        if type in ("FAIL_GATE", "PASS_GATE"):
            delegated_gate = self.check_gate(user, target, end_result, True, context)

            new_exposure = {
                "gate": target,
                "gateValue": "true" if delegated_gate.boolean_value else "false",
                "ruleID": delegated_gate.rule_id
            }

            end_result.secondary_exposures.append(new_exposure)
            if end_result.analytical_condition and isinstance(target, str) and not target.startswith("segment:"):
                end_result.seen_analytical_gates = True

            pass_gate = delegated_gate.boolean_value if type == "PASS_GATE" else not delegated_gate.boolean_value

            end_result.analytical_condition = context.sampling_rate is None
            return pass_gate
        if type in ("MULTI_PASS_GATE", "MULTI_FAIL_GATE"):
            if target is None or len(target) == 0:
                end_result.analytical_condition = context.sampling_rate is None
                return False
            pass_gate = False
            for gate in target:
                other_result = self.check_gate(user, gate, context=context)

                new_exposure = {
                    "gate": gate,
                    "gateValue": "true" if other_result.boolean_value else "false",
                    "ruleID": other_result.rule_id
                }
                end_result.secondary_exposures.append(new_exposure)
                if end_result.analytical_condition and isinstance(target, str) and not target.startswith("segment:"):
                    end_result.seen_analytical_gates = True

                pass_gate = pass_gate or other_result.boolean_value if type == "MULTI_PASS_GATE" else pass_gate or not other_result.boolean_value
                if pass_gate:
                    break

            end_result.analytical_condition = context.sampling_rate is None
            return pass_gate
        if type == "IP_BASED":
            value = self.__get_from_user(user, field)
            if value is None:
                ip = self.__get_from_user(user, "ip")
                if ip is not None and field == "country":
                    if self._disable_country_lookup:
                        logger.warning("Country lookup is disabled but was attempted during evaluation")
                        end_result.evaluation_details = self._create_evaluation_details(
                            EvaluationReason.none, DataSource.COUNTRY_NOT_LOADED)
                        value = None
                    else:
                        if not self._country_lookup:
                            self._country_lookup = CountryLookup()
                        value = self._country_lookup.lookupStr(ip)
            if value is None:
                end_result.analytical_condition = context.sampling_rate is None
                return False
        elif type == "UA_BASED":
            value = self.__get_from_user(user, field)
            if value is None:
                value = self.__get_from_user_agent(user, field, end_result)
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
        elif type == "TARGET_APP":
            if context.client_key is not None:
                value = context.target_app_id
            else:
                value = self._spec_store.get_app_id()

        end_result.analytical_condition = context.sampling_rate is None

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
            return self.__find_string_in_array(
                value, condition)
        if op == "none":
            if user_bucket is not None:
                return not self.__lookup_user_bucket(value, user_bucket)
            return not self.__find_string_in_array(
                value, condition)
        if op == "any_case_sensitive":
            return self.__find_string_in_array(
                value, condition)
        if op == "none_case_sensitive":
            return not self.__find_string_in_array(
                value, condition)
        if op == "str_starts_with_any":
            return self.__match_string_in_array(
                value, target, lambda a, b: a.casefold().startswith(
                    b.casefold()))
        if op == "str_ends_with_any":
            return self.__match_string_in_array(
                value, target, lambda a, b: a.casefold().endswith(
                    b.casefold()))
        if op == "str_contains_any":
            return self.__match_string_in_array(
                value, target, lambda a, b: b.casefold() in a.casefold())
        if op == "str_contains_none":
            return not self.__match_string_in_array(
                value, target, lambda a, b: b.casefold() in a.casefold())
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
        if op == "array_contains_any":
            if not isinstance(value, list):
                return False
            return self.__arrays_have_common_value(value, condition)
        if op == "array_contains_none":
            if not isinstance(value, list):
                return False
            return not self.__arrays_have_common_value(value, condition)
        if op == "array_contains_all":
            if not isinstance(value, list):
                return False
            return self.__arrays_have_all_values(value, condition)
        if op == "not_array_contains_all":
            if not isinstance(value, list):
                return False
            return not self.__arrays_have_all_values(value, condition)

        return False

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
            elif field.casefold() in user.custom:
                value = user.custom[field.casefold()]

        if (value is None or value == "") and self._global_custom_fields is not None:
            if field in self._global_custom_fields:
                value = self._global_custom_fields[field]
            elif field.casefold() in self._global_custom_fields:
                value = self._global_custom_fields[field.casefold()]

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
        return sha256_hash(input)

    def __eval_pass_percentage(self, user, rule, config, salt: Optional[str] = None):
        if rule.get("passPercentage", 0) == 100.0:
            return True
        if rule.get("passPercentage", 0) == 0.0:
            return False
        rule_salt = rule.get("salt", rule.get("id", ""))
        id = self.__get_unit_id(user, rule.get("idType", "userID")) or ""
        config_salt = salt if salt is not None else config.get("salt", "")
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

    def __find_string_in_array(self, value, condition):
        str_value = self.__get_value_as_string(value)
        target = condition.get("fast_target_value")
        op = condition.get("operator")
        if str_value is None or target is None:
            return False
        if op in ('any', 'none'):
            return str_value.casefold() in target
        return str_value in target

    def __arrays_have_common_value(self, value, condition):
        fast_target = condition.get("fast_target_value")
        for target_val in fast_target:
            int_target_val = self.safe_parse_int(target_val)
            if int_target_val and int_target_val in value:
                return True
            if target_val in value:
                return True
        return False

    def __arrays_have_all_values(self, value, condition):
        fast_target = condition.get("fast_target_value")
        for target_val in fast_target:
            int_target_val = self.safe_parse_int(target_val)
            if int_target_val not in value and target_val not in value:
                return False
        return True

    def safe_parse_int(self, value):
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

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

    def __get_from_user_agent(self, user, field, end_result):
        if self._disable_ua_parser:
            logger.warning("UA parser is disabled but was attempted during evaluation")
            end_result.evaluation_details = self._create_evaluation_details(EvaluationReason.none,
                                                                            DataSource.UA_NOT_LOADED)
            return None
        ua = self.__get_from_user(user, "userAgent")
        if ua is None:
            return None

        try:
            if self._ua_parser is None:
                self._ua_parser = load_ua_parser()
            if self._ua_parser is None:
                return None
            parsed = self._ua_parser.Parse(ua)
        except Exception as e:
            logger.warning(f"Error parsing user agent: {e}")
            return None

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
