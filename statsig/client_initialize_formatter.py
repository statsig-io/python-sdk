import base64
from hashlib import sha256


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
    def get_formatted_response(eval_func, user, gates, configs, layers, experiment_to_layer):
        def config_to_response(config_name, config_spec):
            eval_result = eval_func(user, config_spec)
            if eval_result is None:
                return None


            hashed_name = base64.b64encode(
                sha256(config_name.encode('utf-8')).digest()).decode('utf-8')
            result = {
                "name": hashed_name,
                "rule_id": eval_result.rule_id,
                "secondary_exposures": clean_exposures(eval_result.secondary_exposures),
                "value": False
            }

            category = config_spec["type"]
            entity_type = config_spec["entity"]

            if category == "feature_gate":
                if entity_type == "segment" or entity_type == "holdout":
                    return None

                result["value"] = eval_result.boolean_value
            elif category == "dynamic_config":
                id_type = config_spec["idType"]
                result["value"] = eval_result.json_value
                result["group"] = eval_result.rule_id
                result["is_device_based"] = id_type.lower() == "stableid" if isinstance(id_type, str) else False

                if entity_type == "experiment":
                    populate_experiment_fields(config_name, config_spec, eval_result, result)
                elif entity_type == "layer":
                    populate_layer_fields(config_spec, eval_result, result)

            else:
                return None

            return hashed_name, result

        def populate_experiment_fields(config_name: str, config_spec, eval_result, result: dict):
            result["is_user_in_experiment"] = eval_result.is_experiment_group
            result["is_experiment_active"] = config_spec.get('isActive', False) is True

            if not config_spec.get('hasSharedParams', False):
                return

            result["is_in_layer"] = True
            result["explicit_parameters"] = config_spec.get("explicitParameters", [])

            layer_name = experiment_to_layer.get(config_name, None)
            if layer_name is None or layers.get(layer_name, None) is None:
                return

            layer = layers.get(layer_name, {})
            layer_value = layer.get("defaultValue", {})
            current_value = result.get("value", {})
            result["value"] = {**layer_value, **current_value}

        def populate_layer_fields(config_spec, eval_result, result):
            delegate = eval_result.allocated_experiment
            result["explicit_parameters"] = config_spec.get("explicitParameters", [])

            if delegate is not None and delegate != "":
                delegate_spec = configs[delegate]
                delegate_result = eval_func(user, delegate_spec)

                result["allocated_experiment_name"] = hash_name(delegate)
                result["is_user_in_experiment"] = delegate_result.is_experiment_group
                result["is_experiment_active"] = delegate_spec.get("isActive", False) is True
                result["explicit_parameters"] = delegate_spec.get("explicitParameters", [])

            result["undelegated_secondary_exposures"] = clean_exposures(
                eval_result.undelegated_secondary_exposures or [])

        def filter_nones(arr):
            return dict([i for i in arr if i is not None])

        def map_fnc(entry):
            name = entry[0]
            spec = entry[1]
            return config_to_response(name, spec)

        return {
            "feature_gates": filter_nones(map(map_fnc, gates.items())),
            "dynamic_configs": filter_nones(map(map_fnc, configs.items())),
            "layer_configs": filter_nones(map(map_fnc, layers.items())),
            "sdkParams": {},
            "has_updates": True,
            "generator": "statsig-python-sdk",
            "time": 0,
        }