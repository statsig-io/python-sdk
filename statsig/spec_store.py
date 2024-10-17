import json
import threading
from concurrent.futures import wait, ThreadPoolExecutor
from enum import Enum
from typing import List, Optional, Dict, Set, Tuple

from . import globals
from .constants import Const
from .diagnostics import Context, Diagnostics, Marker
from .evaluation_details import EvaluationReason, DataSource
from .sdk_configs import _SDK_Configs
from .spec_updater import SpecUpdater
from .statsig_error_boundary import _StatsigErrorBoundary
from .statsig_network import _StatsigNetwork
from .statsig_options import StatsigOptions
from .utils import djb2_hash


class EntityType(Enum):
    GATE = "feature_gates"
    CONFIG = "dynamic_configs"
    LAYER = "layer_configs"


class _SpecStore:
    _background_download_configs: Optional[threading.Thread]
    _background_download_id_lists: Optional[threading.Thread]

    def __init__(
            self,
            network: _StatsigNetwork,
            options: StatsigOptions,
            statsig_metadata: dict,
            error_boundary: _StatsigErrorBoundary,
            shutdown_event: threading.Event,
            sdk_key: str,
            diagnostics: Diagnostics,
    ):
        self.initial_update_time = 0
        self.init_reason = EvaluationReason.none
        self.init_source = DataSource.UNINITIALIZED
        self._options = options
        self._statsig_metadata = statsig_metadata
        self._error_boundary = error_boundary
        self._shutdown_event = shutdown_event
        self._diagnostics = diagnostics
        self._executor = ThreadPoolExecutor(options.idlist_threadpool_size)

        self._configs: Dict[str, Dict] = {}
        self._gates: Dict[str, Dict] = {}
        self._layers: Dict[str, Dict] = {}
        self._experiment_to_layer: Dict[str, str] = {}
        self._sdk_keys_to_app_ids: Dict[str, str] = {}
        self._hashed_sdk_keys_to_app_ids: Dict[str, str] = {}

        self._id_lists: Dict[str, dict] = {}
        self.unsupported_configs: Set[str] = set()

        self.spec_updater = SpecUpdater(
            network,
            options.data_store,
            options,
            diagnostics,
            sdk_key,
            error_boundary,
            statsig_metadata,
            shutdown_event,
        )

        self.spec_updater.register_process_network_id_lists_listener(
            lambda id_lists: self._process_download_id_lists(id_lists)
        )
        self.spec_updater.register_process_dcs_listener(
            lambda response, reason: self._process_specs(response, reason)
        )

    def initialize(self):
        self._initialize_specs()
        self.initial_update_time = (
            -1
            if self.spec_updater.last_update_time == 0
            else self.spec_updater.last_update_time
        )

        self.spec_updater.download_id_lists(for_initialize=True)

        self.spec_updater.start_background_threads()
        self.spec_updater.initialized = True

    def is_ready_for_checks(self):
        return self.spec_updater.last_update_time != 0

    def last_update_time(self):
        return self.spec_updater.last_update_time

    def shutdown(self):
        if self._options.local_mode:
            return

        self.spec_updater.shutdown()

        self._executor.shutdown(wait=False)

    def get_gate(self, name: str):
        return self._gates.get(name)

    def get_all_gates(self):
        return self._gates

    def get_config(self, name: str):
        return self._configs.get(name)

    def get_all_configs(self):
        return self._configs

    def get_layer(self, name: str):
        return self._layers.get(name)

    def get_all_layers(self):
        return self._layers

    def get_layer_name_for_experiment(self, experiment_name: str):
        return self._experiment_to_layer.get(experiment_name)

    def get_id_list(self, id_list_name):
        return self._id_lists.get(id_list_name)

    def get_all_id_lists(self):
        return self._id_lists

    def get_target_app_for_sdk_key(self, sdk_key=None):
        if sdk_key is None:
            return None
        target_app_id = self._hashed_sdk_keys_to_app_ids.get(djb2_hash(sdk_key))
        if target_app_id is not None:
            return target_app_id
        return self._sdk_keys_to_app_ids.get(sdk_key)

    def _initialize_specs(self):
        initialize_strategies = self._get_initialize_strategy()
        for strategy in initialize_strategies:
            self.spec_updater.get_config_spec(strategy, True)
            if self.init_source is DataSource.BOOTSTRAP or self.last_update_time() != 0:
                self.init_source = strategy
                break

    def _process_specs(self, specs_json, source: DataSource) -> Tuple[bool, bool]:  # has update, parse success
        self._log_process("Processing specs...")
        if specs_json.get("has_updates", False) is False:
            globals.logger.debug("Received update: %s", "No Update")
            return False, True
        if not self.spec_updater.is_specs_json_valid(specs_json):
            self._log_process("Failed to process specs")
            return False, False
        if specs_json.get("time", 0) < self.last_update_time():
            return False, False
        copy = json.dumps(specs_json)
        if callable(self._options.rules_updated_callback):
            self._options.rules_updated_callback(copy)

        def get_parsed_specs(key: str):
            parsed = {}
            for spec in specs_json.get(key, []):
                spec_name = spec.get("name")
                if spec_name is not None:
                    parsed[spec_name] = spec
                parse_target_value_map_from_spec(spec, parsed)
            return parsed

        def parse_target_value_map_from_spec(spec, parsed):
            for rule in spec.get("rules", []):
                for i, cond in enumerate(rule.get("conditions", [])):
                    op = cond.get("operator", None)
                    cond_type = cond.get("type", None)
                    target_value = cond.get("targetValue", [])
                    if op is not None:
                        op = op.lower()
                        if op not in Const.SUPPORTED_OPERATORS:
                            self.unsupported_configs.add(spec.get("name"))
                            del parsed[spec.get("name")]
                    if cond_type is not None:
                        cond_type = cond_type.lower()
                        if cond_type not in Const.SUPPORTED_CONDITION_TYPES:
                            self.unsupported_configs.add(spec.get("name"))
                            del parsed[spec.get("name")]

                    if op in ("any", "none") and cond_type == "user_bucket":
                        rule["conditions"][i]["user_bucket"] = {}
                        for val in target_value:
                            rule["conditions"][i]["user_bucket"][int(val)] = True
                    elif op in ("any", "none") and isinstance(target_value, list):
                        rule["conditions"][i]["fast_target_value"] = {}
                        for val in target_value:
                            rule["conditions"][i]["fast_target_value"][
                                str(val).upper().lower()
                            ] = True
                    elif op in (
                            "any_case_sensitive",
                            "none_case_sensitive",
                    ) and isinstance(target_value, list):
                        rule["conditions"][i]["fast_target_value"] = {}
                        for val in target_value:
                            rule["conditions"][i]["fast_target_value"][str(val)] = True

                    if op in ("array_contains_any", "array_contains_none",
                              "array_contains_all", "not_array_contains_all") and isinstance(target_value, list):
                        rule["conditions"][i]["fast_target_value"] = {}
                        for val in target_value:
                            rule["conditions"][i]["fast_target_value"][str(val)] = True

        self.unsupported_configs.clear()
        new_gates = get_parsed_specs(EntityType.GATE.value)
        new_configs = get_parsed_specs(EntityType.CONFIG.value)
        new_layers = get_parsed_specs(EntityType.LAYER.value)

        new_experiment_to_layer = {}
        layers_dict = specs_json.get("layers", {})
        for layer_name in layers_dict:
            experiments = layers_dict[layer_name]
            for experiment_name in experiments:
                new_experiment_to_layer[experiment_name] = layer_name

        self._sdk_keys_to_app_ids = specs_json.get("sdk_keys_to_app_ids", {})
        self._hashed_sdk_keys_to_app_ids = specs_json.get(
            "hashed_sdk_keys_to_app_ids", {}
        )
        self._gates = new_gates
        self._configs = new_configs
        self._layers = new_layers
        self._experiment_to_layer = new_experiment_to_layer
        self.spec_updater.last_update_time = specs_json.get("time", 0)
        self.init_source = source
        globals.logger.debug("Received update: %s", self.spec_updater.last_update_time)

        flags = specs_json.get("sdk_flags", {})
        _SDK_Configs.set_flags(flags)
        configs = specs_json.get("sdk_configs", {})
        _SDK_Configs.set_configs(configs)

        sampling_rate = specs_json.get("diagnostics", {})
        self._diagnostics.set_sampling_rate(sampling_rate)
        self._log_process("Done processing specs")
        return True, True

    def _process_download_id_lists(self, server_id_lists):
        threw_error = False
        try:
            self._diagnostics.add_marker(
                Marker()
                .get_id_list_sources()
                .process()
                .start({"idListCount": len(server_id_lists)})
            )
            local_id_lists = self._id_lists
            workers = []

            for list_name in server_id_lists:
                server_list = server_id_lists.get(list_name, {})
                url = server_list.get("url", None)
                size = server_list.get("size", 0)
                local_list: dict = local_id_lists.get(list_name, {})

                new_creation_time = server_list.get("creationTime", 0)
                old_creation_time = local_list.get("creationTime", 0)
                new_file_id = server_list.get("fileID", None)
                old_file_id = local_list.get("fileID", "")

                if (
                        url is None
                        or new_creation_time < old_creation_time
                        or new_file_id is None
                ):
                    continue

                # should reset the list if a new file has been created
                if (
                        new_file_id != old_file_id
                        and new_creation_time >= old_creation_time
                ):
                    local_list = {
                        "ids": set(),
                        "readBytes": 0,
                        "url": url,
                        "fileID": new_file_id,
                        "creationTime": new_creation_time,
                    }

                read_bytes = local_list.get("readBytes", 0)
                # check if read bytes count is the same as total file size;
                #  only download additional ids if sizes don't match
                if size <= read_bytes or url == "":
                    continue

                if self._shutdown_event.is_set():
                    return

                future = self._executor.submit(
                    self.spec_updater.download_single_id_list,
                    url,
                    list_name,
                    local_list,
                    local_id_lists,
                    read_bytes,
                )
                workers.append(future)

            wait(workers, self._options.idlists_sync_interval)

            deleted_lists = []
            for list_name in local_id_lists:
                if list_name not in server_id_lists:
                    deleted_lists.append(list_name)

            # remove any list that has been deleted
            for list_name in deleted_lists:
                local_id_lists.pop(list_name, None)

        except Exception as e:
            threw_error = True
            self._error_boundary.log_exception("_download_id_lists_process", e)
        finally:
            self._diagnostics.add_marker(
                Marker()
                .get_id_list_sources()
                .process()
                .end({"success": not threw_error})
            )

    def _sync(self, sync_func, interval, fast_start=False):
        if fast_start:
            sync_func()

        while True:
            try:
                if self._shutdown_event.wait(interval):
                    break
                sync_func()
            except Exception as e:
                self._error_boundary.log_exception("_sync", e)

    def _log_process(self, msg, process=None):
        if process is None:
            process = "Initialize" if not self.spec_updater.initialized else "Config Sync"
        globals.logger.log_process(process, msg)

    def _get_current_context(self):
        return (
            Context.INITIALIZE
            if not self.spec_updater.initialized
            else Context.CONFIG_SYNC
        )

    def _get_initialize_strategy(self) -> List[DataSource]:
        try:
            if self._options.initialize_sources is not None:
                return self._options.initialize_sources
            strategies = [DataSource.NETWORK]
            data_store = self._options.data_store
            if data_store is not None:
                strategies.insert(0, DataSource.DATASTORE)
            if self._options.bootstrap_values:
                if data_store is not None:
                    globals.logger.debug(
                        "data_store gets priority over bootstrap_values. bootstrap_values will be ignored")
                else:
                    strategies.insert(0, DataSource.BOOTSTRAP)
            if self._options.fallback_to_statsig_api:
                strategies.append(DataSource.STATSIG_NETWORK)

            return strategies
        except Exception:
            globals.logger.warning(
                "Failed to get initialization sources, fallling back to always sync from statsig network "
            )
            return [DataSource.STATSIG_NETWORK]
