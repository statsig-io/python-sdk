import base64
import random
from hashlib import sha256
from typing import Any, Dict, Optional, Union

from .statsig_metadata import _StatsigMetadata
from .config_evaluation import _ConfigEvaluation
from .statsig_user import StatsigUser
from .spec_store import _SpecStore
from .utils import HashingAlgorithm, djb2_hash


def hash_name(name: str, algorithm: HashingAlgorithm):
    if algorithm == HashingAlgorithm.NONE:
        return name
    if algorithm == HashingAlgorithm.DJB2:
        return djb2_hash(name)
    return base64.b64encode(
        sha256(name.encode('utf-8')).digest()).decode('utf-8')


ClientInitializeResponse = Optional[Dict[str, Any]]


class ClientInitializeResponseFormatter:

    @staticmethod
    def get_formatted_response(
            eval_func, user: StatsigUser,
            spec_store: _SpecStore,
            evaluator,
            hash_algo: HashingAlgorithm,
            client_sdk_key=None,
            include_local_override=False
    ) -> ClientInitializeResponse:
        def config_to_response(config_name, config_spec):
            target_app_id = spec_store.get_target_app_for_sdk_key(client_sdk_key)
            config_target_apps = config_spec.get("targetAppIDs", [])
            if target_app_id is not None and target_app_id not in config_target_apps:
                return None

            eval_result = _ConfigEvaluation()
            local_override = None
            category = config_spec["type"]
            if include_local_override:
                if category == "feature_gate":
                    local_override = evaluator.lookup_gate_override(user, config_name)
                if category == "dynamic_config":
                    local_override = evaluator.lookup_config_override(user, config_name)

            if local_override is not None:
                eval_result = local_override
            else:
                eval_func(user, config_spec, eval_result)

            if eval_result is None:
                return None

            hashed_name = hash_name(config_name, hash_algo)
            result = {
                "name": hashed_name,
                "rule_id": eval_result.rule_id,
                "secondary_exposures": hash_exposures(eval_result.secondary_exposures, hash_algo),
                "value": False
            }

            category = config_spec["type"]
            entity_type = config_spec["entity"]

            if category == "feature_gate":
                if entity_type in ("segment", "holdout"):
                    return None

                result["value"] = eval_result.boolean_value
                result["id_type"] = config_spec["idType"]
            elif category == "dynamic_config":
                id_type = config_spec["idType"]
                result["value"] = eval_result.json_value
                result["group"] = eval_result.rule_id
                result["passed"] = eval_result.boolean_value
                result["is_device_based"] = id_type.lower(
                ) == "stableid" if isinstance(id_type, str) else False

                if entity_type != "layer":
                    result["id_type"] = config_spec["idType"]

                if entity_type == "experiment":
                    populate_experiment_fields(
                        config_name, config_spec, eval_result, result)
                elif entity_type == "layer":
                    populate_layer_fields(config_spec, eval_result, result, hash_algo)
                elif entity_type == "autotune":
                    result["group_name"] = eval_result.group_name

            else:
                return None

            return hashed_name, result

        def populate_experiment_fields(
                config_name: str, config_spec, eval_result, result: dict):
            result["is_user_in_experiment"] = eval_result.is_experiment_group
            result["is_experiment_active"] = config_spec.get(
                'isActive', False) is True
            if eval_result.group_name is not None:
                result["group_name"] = eval_result.group_name

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

        def populate_layer_fields(config_spec, eval_result, result, hash_algo):
            delegate = eval_result.allocated_experiment
            result["explicit_parameters"] = config_spec.get(
                "explicitParameters", [])

            if delegate is not None and delegate != "":
                delegate_spec = spec_store.get_config(delegate)
                delegate_result = _ConfigEvaluation()
                eval_func(user, delegate_spec, delegate_result)

                if delegate_spec is not None:
                    result["allocated_experiment_name"] = hash_name(delegate, hash_algo)
                    result["is_user_in_experiment"] = delegate_result.is_experiment_group
                    result["is_experiment_active"] = delegate_spec.get(
                        "isActive", False) is True
                    result["explicit_parameters"] = delegate_spec.get(
                        "explicitParameters", [])
                    if delegate_result.group_name is not None:
                        result["group_name"] = delegate_result.group_name

            result["undelegated_secondary_exposures"] = eval_result.undelegated_secondary_exposures or []

        def hash_exposures(exposures: list, algo: HashingAlgorithm):
            for exposure in exposures:
                exposure['gate'] = hash_name(exposure['gate'], algo)
            return exposures

        def filter_nones(arr):
            return dict([i for i in arr if i is not None])

        def map_fnc(entry):
            name = entry[0]
            spec = entry[1]
            return config_to_response(name, spec)

        evaluated_keys: Dict[str, Union[str, Dict[str, str]]] = {}
        if user.user_id is not None:
            evaluated_keys["userID"] = user.user_id

        if user.custom_ids is not None:
            evaluated_keys["customIDs"] = user.custom_ids

        meta = _StatsigMetadata.get()
        result = {
            "feature_gates": filter_nones(map(map_fnc, spec_store.get_all_gates().items())),
            "dynamic_configs": filter_nones(map(map_fnc, spec_store.get_all_configs().items())),
            "layer_configs": filter_nones(map(map_fnc, spec_store.get_all_layers().items())),
            "sdkParams": {},
            "has_updates": True,
            "generator": "statsig-python-sdk",
            "evaluated_keys": evaluated_keys,
            "time": spec_store.last_update_time(),
            "user": user.to_dict(),
            "hash_used": hash_algo.value,
            "sdkInfo": {
                "sdkType": meta["sdkType"],
                "sdkVersion": meta["sdkVersion"],
            }
        }
        session_replay_info = spec_store.get_session_replay_info()
        if session_replay_info is not None:
            result["recording_blocked"] = session_replay_info.get("recording_blocked", False)
            can_record = result["recording_blocked"] is False
            targeting_gate_name = session_replay_info.get("targeting_gate", None)
            if targeting_gate_name is not None:
                targeting_gate = result["feature_gates"].get(
                    hash_name(targeting_gate_name, hash_algo), None)
                if targeting_gate is not None:
                    result["passes_session_recording_targeting"] = targeting_gate.get("value", False)
                    if not result["passes_session_recording_targeting"]:
                        can_record = False
            sampling_rate = session_replay_info.get("sampling_rate", None)
            rand = random.random()
            if sampling_rate is not None:
                result["session_recording_rate"] = sampling_rate
                if rand > sampling_rate:
                    can_record = False
            result["can_record_session"] = can_record
            session_recording_event_triggers: Dict[str, Dict] = session_replay_info.get("session_recording_event_triggers", None)
            if session_recording_event_triggers is not None:
                result["session_recording_event_triggers"] = {}
                for event in session_recording_event_triggers:
                    event_trigger = session_recording_event_triggers[event]
                    result["session_recording_event_triggers"][event] = {}
                    if event_trigger.get("values", None) is not None:
                        result["session_recording_event_triggers"][event]["values"] = event_trigger["values"]
                    event_sampling_rate = event_trigger.get("sampling_rate", None)
                    if event_sampling_rate is not None:
                        result["session_recording_event_triggers"][event]["passes_sampling"] = rand <= event_sampling_rate

            session_recording_exposure_triggers: Dict[str, Dict] = session_replay_info.get("session_recording_exposure_triggers", None)
            if session_recording_exposure_triggers is not None:
                result["session_recording_exposure_triggers"] = {}
                for exposure in session_recording_exposure_triggers:
                    exposure_trigger = session_recording_exposure_triggers[exposure]
                    result["session_recording_exposure_triggers"][hash_name(exposure, hash_algo)] = {}
                    if exposure_trigger.get("values", None) is not None:
                        result["session_recording_exposure_triggers"][hash_name(exposure, hash_algo)]["values"] = exposure_trigger["values"]
                    event_sampling_rate = exposure_trigger.get("sampling_rate", None)
                    if event_sampling_rate is not None:
                        result["session_recording_exposure_triggers"][hash_name(exposure, hash_algo)]["passes_sampling"] = rand <= event_sampling_rate
        return result
