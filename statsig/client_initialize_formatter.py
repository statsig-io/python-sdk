import base64
from hashlib import sha256

from .statsig_user import StatsigUser
from .spec_store import _SpecStore


def hash_name(name: str):
    return base64.b64encode(
        sha256(name.encode('utf-8')).digest()).decode('utf-8')


def clean_exposures(exposures):
    seen = {}
    result = []
    for exposure in exposures:
        key = f"{exposure['gate']}|{exposure['gateValue']}|{exposure['ruleID']}"
        if not seen.get(key, False):
            seen[key] = True
            result.append(exposure)
    return result


class ClientInitializeResponseFormatter:

    @staticmethod
    def get_formatted_response(
            eval_func, user: StatsigUser, spec_store: _SpecStore):
        def config_to_response(config_name, config_spec):
            eval_result = eval_func(user, config_spec)
            if eval_result is None:
                return None

            hashed_name = hash_name(config_name)
            result = {
                "name": hashed_name,
                "rule_id": eval_result.rule_id,
                "secondary_exposures": clean_exposures(eval_result.secondary_exposures),
                "value": False
            }

            category = config_spec["type"]
            entity_type = config_spec["entity"]

            if category == "feature_gate":
                if entity_type in ("segment", "holdout"):
                    return None

                result["value"] = eval_result.boolean_value
            elif category == "dynamic_config":
                id_type = config_spec["idType"]
                result["value"] = eval_result.json_value
                result["group"] = eval_result.rule_id
                result["is_device_based"] = id_type.lower(
                ) == "stableid" if isinstance(id_type, str) else False

                if entity_type == "experiment":
                    populate_experiment_fields(
                        config_name, config_spec, eval_result, result)
                elif entity_type == "layer":
                    populate_layer_fields(config_spec, eval_result, result)

            else:
                return None

            return hashed_name, result

        def populate_experiment_fields(
                config_name: str, config_spec, eval_result, result: dict):
            result["is_user_in_experiment"] = eval_result.is_experiment_group
            result["is_experiment_active"] = config_spec.get(
                'isActive', False) is True

            if not config_spec.get('hasSharedParams', False):
                return

            result["is_in_layer"] = True
            result["explicit_parameters"] = config_spec.get(
                "explicitParameters", [])

            layer_name = spec_store.get_layer_name_for_experiment(config_name)
            if layer_name is None or spec_store.get_layer(layer_name) is None:
                return

            layer = spec_store.get_layer(layer_name)
            if layer is None:
                return

            layer_value = layer.get("defaultValue", {})
            current_value = result.get("value", {})
            result["value"] = {**layer_value, **current_value}

        def populate_layer_fields(config_spec, eval_result, result):
            delegate = eval_result.allocated_experiment
            result["explicit_parameters"] = config_spec.get(
                "explicitParameters", [])

            if delegate is not None and delegate != "":
                delegate_spec = spec_store.get_config(delegate)
                delegate_result = eval_func(user, delegate_spec)

                if delegate_spec is not None:
                    result["allocated_experiment_name"] = hash_name(delegate)
                    result["is_user_in_experiment"] = delegate_result.is_experiment_group
                    result["is_experiment_active"] = delegate_spec.get(
                        "isActive", False) is True
                    result["explicit_parameters"] = delegate_spec.get(
                        "explicitParameters", [])

            result["undelegated_secondary_exposures"] = clean_exposures(
                eval_result.undelegated_secondary_exposures or [])

        def filter_nones(arr):
            return dict([i for i in arr if i is not None])

        def map_fnc(entry):
            name = entry[0]
            spec = entry[1]
            return config_to_response(name, spec)

        evaluated_keys = {}
        if user.user_id is not None:
            evaluated_keys["userID"] = user.user_id

        if user.custom_ids is not None:
            evaluated_keys["customIDs"] = user.custom_ids

        return {
            "feature_gates": filter_nones(map(map_fnc, spec_store.get_all_gates().items())),
            "dynamic_configs": filter_nones(map(map_fnc, spec_store.get_all_configs().items())),
            "layer_configs": filter_nones(map(map_fnc, spec_store.get_all_layers().items())),
            "sdkParams": {},
            "has_updates": True,
            "generator": "statsig-python-sdk",
            "evaluated_keys": evaluated_keys,
            "time": 0,
        }
