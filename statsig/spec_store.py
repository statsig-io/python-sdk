import json
import threading
from concurrent.futures import ThreadPoolExecutor, wait
from typing import Optional, Dict, Set

from .constants import Const
from .sdk_flags import _SDKFlags
from .utils import djb2_hash

from .evaluation_details import EvaluationReason
from .statsig_error_boundary import _StatsigErrorBoundary
from .statsig_errors import StatsigValueError, StatsigNameError
from .statsig_network import _StatsigNetwork
from .statsig_options import StatsigOptions
from .thread_util import spawn_background_thread, THREAD_JOIN_TIMEOUT
from .diagnostics import Context, Diagnostics, Marker, Key
from . import globals

RULESETS_SYNC_INTERVAL = 10
IDLISTS_SYNC_INTERVAL = 60
STORAGE_ADAPTER_KEY = "statsig.cache"
SYNC_OUTDATED_MAX_S = 120

class _SpecStore:
    _background_download_configs: Optional[threading.Thread]
    _background_download_id_lists: Optional[threading.Thread]

    def __init__(self, network: _StatsigNetwork, options: StatsigOptions, statsig_metadata: dict,
                 error_boundary: _StatsigErrorBoundary, shutdown_event: threading.Event, sdk_key: str, diagnostics: Diagnostics):
        self.last_update_time = 0
        self.initial_update_time = 0
        self.init_reason = EvaluationReason.uninitialized
        self._initialized = False
        self._network = network
        self._options = options
        self._statsig_metadata = statsig_metadata
        self._error_boundary = error_boundary
        self._shutdown_event = shutdown_event
        self._diagnostics = diagnostics
        self._executor = ThreadPoolExecutor(options.idlist_threadpool_size)
        self._background_download_configs = None
        self._background_download_id_lists = None
        self._sync_failure_count = 0
        self._sdk_key = sdk_key

        self._configs: Dict[str, Dict] = {}
        self._gates: Dict[str, Dict] = {}
        self._layers: Dict[str, Dict] = {}
        self._experiment_to_layer: Dict[str, str] = {}
        self._sdk_keys_to_app_ids: Dict[str, str] = {}
        self._hashed_sdk_keys_to_app_ids: Dict[str, str] = {}

        self._id_lists: Dict[str, dict] = {}
        self.unsupported_configs: Set[str] = set()

    def _is_specs_json_valid(self, specs_json):
        if specs_json is None or specs_json.get("time") is None:
            return False
        hashed_sdk_key_used = specs_json.get("hashed_sdk_key_used", None)
        if hashed_sdk_key_used is not None and hashed_sdk_key_used != djb2_hash(self._sdk_key):
            return False
        if specs_json.get("has_updates", False) is False:
            return False
        return True

    def initialize(self):
        self._initialize_specs()
        self.initial_update_time = -1 if self.last_update_time == 0 else self.last_update_time

        self._download_id_lists(for_initialize=True)

        self.spawn_bg_threads_if_needed()
        self._initialized = True

    def is_ready_for_checks(self):
        return self.last_update_time != 0

    def spawn_bg_threads_if_needed(self):
        if self._options.local_mode:
            return
        self._diagnostics.set_context(Context.CONFIG_SYNC)

        if self._background_download_configs is None or not self._background_download_configs.is_alive():
            self._spawn_bg_download_config_specs()

        if self._background_download_id_lists is None or not self._background_download_id_lists.is_alive():
            self._spawn_bg_download_id_lists()

    def shutdown(self):
        if self._options.local_mode:
            return

        if self._background_download_configs is not None:
            self._background_download_configs.join(THREAD_JOIN_TIMEOUT)

        if self._background_download_id_lists is not None:
            self._background_download_id_lists.join(THREAD_JOIN_TIMEOUT)

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
        if self._options.data_store is not None:
            if self._options.bootstrap_values is not None:
                globals.logger.debug(
                    "data_store gets priority over bootstrap_values. bootstrap_values will be ignored")
            self._load_config_specs_from_storage_adapter()
            if self.last_update_time == 0:
                self._log_process("Retrying with network...")
                self._download_config_specs(for_initialize=True)

        elif self._options.bootstrap_values is not None:
            self._bootstrap_config_specs()

        # If no updates from bootstrap or data_store, try to initialize from network
        if self.init_reason is not EvaluationReason.bootstrap and self.last_update_time == 0:
            self._download_config_specs(for_initialize=True)

    def _process_specs(self, specs_json) -> bool:
        self._log_process("Processing specs...")
        if not self._is_specs_json_valid(specs_json):
            self._log_process("Failed to process specs")
            return False
        if specs_json.get("time", 0) < self.last_update_time:
            return False
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

                    if op in ('any', 'none') and cond_type == "user_bucket":
                        user_bucket_array = cond.get("targetValue", [])
                        if len(user_bucket_array) == 0:
                            return
                        rule["conditions"][i]["user_bucket"] = {}
                        for val in user_bucket_array:
                            rule["conditions"][i]["user_bucket"][int(val)] = True

        self.unsupported_configs.clear()
        new_gates = get_parsed_specs("feature_gates")
        new_configs = get_parsed_specs("dynamic_configs")
        new_layers = get_parsed_specs("layer_configs")

        new_experiment_to_layer = {}
        layers_dict = specs_json.get("layers", {})
        for layer_name in layers_dict:
            experiments = layers_dict[layer_name]
            for experiment_name in experiments:
                new_experiment_to_layer[experiment_name] = layer_name

        self._sdk_keys_to_app_ids = specs_json.get("sdk_keys_to_app_ids", {})
        self._hashed_sdk_keys_to_app_ids = specs_json.get("hashed_sdk_keys_to_app_ids", {})
        self._gates = new_gates
        self._configs = new_configs
        self._layers = new_layers
        self._experiment_to_layer = new_experiment_to_layer
        self.last_update_time = specs_json.get("time", 0)

        flags = specs_json.get("sdk_flags", {})
        _SDKFlags.set_flags(flags)

        sampling_rate = specs_json.get("diagnostics", {})
        self._diagnostics.set_sampling_rate(sampling_rate)

        self._log_process("Done processing specs")
        return True

    def _bootstrap_config_specs(self):
        self._diagnostics.add_marker(Marker().bootstrap().process().start())
        if self._options.bootstrap_values is None:
            return

        try:
            specs = json.loads(self._options.bootstrap_values)
            if specs is None or not self._is_specs_json_valid(specs):
                return
            if self._process_specs(specs):
                self.init_reason = EvaluationReason.bootstrap

        except ValueError:
            # JSON decoding failed, just let background thread update rulesets
            globals.logger.error(
                'Failed to parse bootstrap_values')
        finally:
            self._diagnostics.add_marker(Marker().bootstrap().process().end(
                {'success': self.init_reason is EvaluationReason.bootstrap}))

    def _spawn_bg_download_config_specs(self):
        interval = self._options.rulesets_sync_interval or RULESETS_SYNC_INTERVAL
        fast_start = self._sync_failure_count > 0

        if self._options.data_store is not None and self._options.data_store.should_be_used_for_querying_updates(STORAGE_ADAPTER_KEY):
            self._background_download_configs = spawn_background_thread(
                "bg_download_config_specs_from_storage_adapter",
                self._sync,
                (self._load_config_specs_from_storage_adapter, interval, fast_start),
                self._error_boundary)
        else:
            self._background_download_configs = spawn_background_thread(
                "bg_download_config_specs",
                self._sync,
                (self._download_config_specs, interval, fast_start),
                self._error_boundary)

    def _download_config_specs(self, for_initialize=False):
        self._log_process("Loading specs from network...")
        log_on_exception = not self._initialized

        timeout: Optional[int] = None
        if for_initialize:
            timeout = self._options.init_timeout

        if self._sync_failure_count * self._options.rulesets_sync_interval > 120:
            log_on_exception = True
            self._sync_failure_count = 0

        try:
            specs = self._network.download_config_specs(
                self.last_update_time, log_on_exception, timeout)

            if specs is None:
                self._sync_failure_count += 1
                return

            self.download_config_spec_process(specs)
        except Exception as e:
            raise e
        finally:
            self._diagnostics.log_diagnostics(Context.CONFIG_SYNC, Key.DOWNLOAD_CONFIG_SPECS)

    def download_config_spec_process(self, specs):
        try:
            self._diagnostics.add_marker(Marker().download_config_specs().process().start())

            self._log_process("Done loading specs")
            if self._process_specs(specs):
                self._save_to_storage_adapter(specs)
                self.init_reason = EvaluationReason.network
        except Exception as e:
            raise e
        finally:
            self._diagnostics.add_marker(Marker().download_config_specs().process().end(
                {'success': self.init_reason == EvaluationReason.network}))

    def _save_to_storage_adapter(self, specs):
        if not self._is_specs_json_valid(specs):
            return

        if self._options.data_store is None:
            return

        if self.last_update_time == 0:
            return

        self._options.data_store.set(STORAGE_ADAPTER_KEY, json.dumps(specs))

    def _load_config_specs_from_storage_adapter(self):
        self._log_process("Loading specs from adapter")
        if self._options.data_store is None:
            return

        self._diagnostics.add_marker(Marker().data_store_config_specs().process().start())

        cache_string = self._options.data_store.get(STORAGE_ADAPTER_KEY)
        if not isinstance(cache_string, str):
            return

        cache = json.loads(cache_string)
        if not isinstance(cache, dict):
            globals.logger.warning(
                "Invalid type returned from StatsigOptions.data_store")
            return
        adapter_time = cache.get("time", None)
        if not isinstance(adapter_time,
                          int) or adapter_time < self.last_update_time:
            return

        self._log_process("Done loading specs")
        if self._process_specs(cache):
            self.init_reason = EvaluationReason.data_adapter

        self._diagnostics.add_marker(Marker().data_store_config_specs().process().end(
                {'success': self.init_reason == EvaluationReason.data_adapter}))
        self._diagnostics.log_diagnostics(Context.CONFIG_SYNC, Key.DATA_STORE_CONFIG_SPECS)

    def _spawn_bg_download_id_lists(self):

        interval = self._options.idlists_sync_interval or IDLISTS_SYNC_INTERVAL
        self._background_download_id_lists = spawn_background_thread(
            "bg_download_id_lists",
            self._sync,
            (self._download_id_lists, interval),
            self._error_boundary)

    def _download_id_lists(self, for_initialize=False):
        try:
            timeout: Optional[int] = None
            if for_initialize:
                timeout = self._options.init_timeout

            server_id_lists = self._network.get_id_lists(timeout=timeout)

            if server_id_lists is None:
                return
            self._download_id_lists_process(server_id_lists)
        except Exception as e:
            raise e
        finally:
            self._diagnostics.log_diagnostics(Context.CONFIG_SYNC, Key.GET_ID_LIST)

    def _download_id_lists_process(self, server_id_lists):
        threw_error = False
        try:
            self._diagnostics.add_marker(Marker().get_id_list_sources().process().start(
                {'idListCount': len(server_id_lists)}))
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

                if url is None or new_creation_time < old_creation_time or new_file_id is None:
                    continue

                # should reset the list if a new file has been created
                if new_file_id != old_file_id and new_creation_time >= old_creation_time:
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
                    self._download_single_id_list,
                    url, list_name, local_list, local_id_lists, read_bytes
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
            self._diagnostics.add_marker(Marker().get_id_list_sources().process().end({'success': not threw_error}))

    def _download_single_id_list(
            self, url, list_name, local_list, all_lists, start_index):
        resp = self._network.get_id_list(
            url, headers={"Range": f"bytes={start_index}-"})
        if resp is None:
            return
        threw_error = False
        try:
            self._diagnostics.add_marker(Marker().get_id_list().process().start({'url': url}))
            content_length_str = resp.headers.get('content-length')
            if content_length_str is None:
                raise StatsigValueError("Content length invalid.")
            content_length = int(content_length_str)
            content = resp.text
            if content is None:
                return
            first_char = content[0]
            if first_char not in ('+', '-'):
                raise StatsigNameError("Seek range invalid.")
            lines = content.splitlines()
            for line in lines:
                if len(line) <= 1:
                    continue
                op = line[0]
                id = line[1:].strip()
                if op == "+":
                    local_list.get("ids", set()).add(id)
                elif op == "-":
                    local_list.get("ids", set()).discard(id)
            local_list["readBytes"] = start_index + content_length
            all_lists[list_name] = local_list
        except Exception as e:
            threw_error = True
            self._error_boundary.log_exception("_download_single_id_list", e)
        finally:
            self._diagnostics.add_marker(Marker().get_id_list().process().end({
                'url': url,
                'success': not threw_error,
            }))

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
            process = "Initialize" if not self._initialized else "Sync"
        globals.logger.log_process(process, msg)

    def _get_current_context(self):
        return Context.INITIALIZE if not self._initialized else Context.CONFIG_SYNC
