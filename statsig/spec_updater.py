import json
import threading
import time
from typing import Optional, Callable, List, Tuple

from . import globals
from .diagnostics import Diagnostics, Marker, Context, Key
from .evaluation_details import DataSource
from .http_worker import RequestResult
from .interface_data_store import IDataStore
from .interface_network import IStreamingListeners
from .statsig_context import InitContext
from .statsig_error_boundary import _StatsigErrorBoundary
from .statsig_errors import StatsigValueError, StatsigNameError
from .statsig_network import _StatsigNetwork
from .statsig_options import StatsigOptions
from .thread_util import spawn_background_thread, THREAD_JOIN_TIMEOUT
from .utils import djb2_hash

RULESETS_SYNC_INTERVAL = 10
IDLISTS_SYNC_INTERVAL = 60
SYNC_OUTDATED_MAX_S = 120
STORAGE_ADAPTER_KEY = "statsig.cache"


class SpecUpdater:
    def __init__(
            self,
            network: _StatsigNetwork,
            data_adapter: Optional[IDataStore],
            options: StatsigOptions,
            diagnostics: Diagnostics,
            sdk_key: str,
            error_boundary: _StatsigErrorBoundary,
            statsig_metadata: dict,
            shutdown_event: threading.Event,
            context: InitContext
    ):
        self._shutdown_event = shutdown_event
        self._sync_failure_count = 0
        self._network = network
        self._options = options
        self._diagnostics = diagnostics
        self._sdk_key = sdk_key
        self._error_boundary = error_boundary
        self._statsig_metadata = statsig_metadata
        self._background_download_configs = None
        self._background_download_id_lists = None
        self._config_sync_strategies = self._get_sync_dcs_strategies()
        self._dcs_process_lock = threading.Lock()
        if options.out_of_sync_threshold_in_s is not None:
            self._enforce_sync_fallback_threshold_in_ms: Optional[float] = options.out_of_sync_threshold_in_s * 1000
        else:
            self._enforce_sync_fallback_threshold_in_ms = None

        self.initialized = False
        self.last_update_time = 0
        self.initial_update_time = 0
        self.dcs_listener: Optional[Callable] = None
        self.id_lists_listener: Optional[Callable] = None
        self.data_adapter = data_adapter
        self.context = context

    def get_config_spec(self, source: DataSource, for_initialize=False):
        try:
            self._log_process(f"Loading specs from {source.value}...",
                              "Initialize" if for_initialize else "Config Sync")
            init_timeout = None
            if for_initialize:
                init_timeout = self._options.init_timeout
            if source is DataSource.DATASTORE:
                self.load_config_specs_from_storage_adapter()
            elif source is DataSource.BOOTSTRAP:
                self.bootstrap_config_specs()
            elif source is DataSource.NETWORK:
                self._network.get_dcs(
                    self._on_dcs_complete, self.last_update_time, True, init_timeout
                )
            elif source is DataSource.STATSIG_NETWORK:
                self._network.get_dcs_fallback(
                    self._on_dcs_complete, self.last_update_time, True, init_timeout
                )
        except Exception as e:
            if not for_initialize:
                self._sync_failure_count += 1
            self._error_boundary.log_exception(f"get_config_spec:{source}", e)

    def register_process_network_id_lists_listener(self, listener: Callable):
        self.id_lists_listener = listener

    def register_process_dcs_listener(self, listener: Callable):
        def dcs_listener_with_lock(spec_json, source: DataSource) -> bool:
            with self._dcs_process_lock:
                return listener(spec_json, source)

        self.dcs_listener = dcs_listener_with_lock

    def load_config_specs_from_storage_adapter(self) -> bool:
        def load():
            try:
                if self._options.data_store is None:
                    return False

                self._diagnostics.add_marker(
                    Marker().data_store_config_specs().process().start()
                )

                cache_string = self._options.data_store.get(STORAGE_ADAPTER_KEY)
                if not isinstance(cache_string, str):
                    return False

                cache = json.loads(cache_string)
                if not isinstance(cache, dict):
                    globals.logger.warning(
                        "Invalid type returned from StatsigOptions.data_store"
                    )
                    return False
                adapter_time = cache.get("time", None)
                if not isinstance(adapter_time, int) or adapter_time < self.last_update_time:
                    return False

                self._log_process("Done loading specs")
                _, parse_success = False, False
                if self.dcs_listener is not None:
                    _, parse_success = self.dcs_listener(cache, DataSource.DATASTORE)
                self._diagnostics.add_marker(
                    Marker()
                    .data_store_config_specs()
                    .process()
                    .end({"success": parse_success})
                )
                return parse_success

            except Exception as err:
                self._diagnostics.add_marker(
                    Marker()
                    .data_store_config_specs()
                    .process()
                    .end(
                        {"success": False, "error": err.__dict__},
                    )
                )
                return False
            finally:
                self._diagnostics.log_diagnostics(
                    Context.CONFIG_SYNC, Key.DATA_STORE_CONFIG_SPECS
                )

        success = load()
        if success is False:
            self._sync_failure_count += 1
        return success

    def _on_dcs_complete(self, data_source: DataSource, specs: Optional[dict], error: Optional[Exception]):
        def process() -> Tuple[bool, Optional[Exception]]:
            if error is not None:
                return False, error

            if specs is None:
                return False, StatsigValueError("Failed to download specs from network")
            err = None
            try:
                self._diagnostics.add_marker(
                    Marker().download_config_specs().process().start()
                )
                self._log_process("Done loading specs")
                has_update, parse_success = False, False  # parce success can be true even if there is no update
                if self.dcs_listener is not None:
                    has_update, parse_success = self.dcs_listener(specs, data_source)
                if has_update:
                    self._save_to_storage_adapter(specs)
                return parse_success, None
            except Exception as e:
                return False, e
            finally:
                self._diagnostics.add_marker(
                    Marker()
                    .download_config_specs()
                    .process()
                    .end(
                        {"success": err is None, "error": Diagnostics.format_error(err)}
                    )
                )

        parse_success, error = process()
        if parse_success is False:
            self._sync_failure_count += 1  # increment sync failure to trigger fallback behavior

    def _log_process(self, msg, process=None):
        if process is None:
            process = "Initialize" if not self.initialized else "Config Sync"
        globals.logger.log_process(process, msg)

    def _save_to_storage_adapter(self, specs):
        if not self.is_specs_json_valid(specs):
            return

        if self._options.data_store is None:
            return

        if self.last_update_time == 0:
            return

        self._options.data_store.set(STORAGE_ADAPTER_KEY, json.dumps(specs))

    def is_specs_json_valid(self, specs_json):
        if specs_json is None or specs_json.get("time") is None:
            return False
        hashed_sdk_key_used = specs_json.get("hashed_sdk_key_used", None)
        if hashed_sdk_key_used is not None and hashed_sdk_key_used != djb2_hash(
                self._sdk_key
        ):
            return False
        return True

    def bootstrap_config_specs(self):
        self._diagnostics.add_marker(Marker().bootstrap().process().start())
        if self._options.bootstrap_values is None:
            return

        _, success = False, False

        try:
            specs = json.loads(self._options.bootstrap_values)
            if specs is None or not self.is_specs_json_valid(specs):
                return
            if self.dcs_listener is not None:
                _, success = self.dcs_listener(specs, DataSource.BOOTSTRAP)

        except ValueError:
            # JSON decoding failed, just let background thread update rulesets
            globals.logger.error("Failed to parse bootstrap_values")
        finally:
            self._diagnostics.add_marker(
                Marker().bootstrap().process().end({"success": success})
            )

    def download_id_lists(self, for_initialize=False):
        def on_complete(id_lists: list, error: Exception):
            if error is not None:
                self._error_boundary.log_exception("_download_id_lists", error)
                return
            if id_lists is None:
                return
            result[0] = True
            if self.id_lists_listener is not None:
                self.id_lists_listener(id_lists)

        result: List[bool] = [False]

        try:
            init_timeout: Optional[int] = None
            if for_initialize:
                init_timeout = self._options.init_timeout

            self._network.get_id_lists(on_complete, False, init_timeout)
            if result[0] is False and self._options.fallback_to_statsig_api:
                self._network.get_id_lists_fallback(on_complete, False, init_timeout)

        except Exception as e:
            raise e
        finally:
            self._diagnostics.log_diagnostics(Context.CONFIG_SYNC, Key.GET_ID_LIST)

    def download_single_id_list(
            self, url, list_name, local_list, all_lists, start_index
    ):
        def on_complete(resp: RequestResult):
            if resp is None:
                return
            threw_error = False
            try:
                self._diagnostics.add_marker(
                    Marker().get_id_list().process().start({"url": url})
                )
                content_length_str = resp.headers.get("content-length") if resp.headers else None
                if content_length_str is None:
                    raise StatsigValueError("Content length invalid.")
                content_length = int(content_length_str)
                content = resp.text
                if content is None:
                    return
                first_char = content[0]
                if first_char not in ("+", "-"):
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
                self._diagnostics.add_marker(
                    Marker()
                    .get_id_list()
                    .process()
                    .end(
                        {
                            "url": url,
                            "success": not threw_error,
                        }
                    )
                )

        self._network.get_id_list(
            on_complete, url, headers={"Range": f"bytes={start_index}-"}
        )

    def start_background_threads(self):
        if self._options.local_mode:
            return
        self._diagnostics.set_context(Context.CONFIG_SYNC)
        if self._network.is_pull_worker("download_config_specs"):
            if (
                    self._background_download_configs is None
                    or not self._background_download_configs.is_alive()
            ):
                self._spawn_bg_poll_dcs()
        else:

            def on_update_dcs(specs: dict, lcut: int):
                if self.last_update_time > lcut:
                    return
                if self.dcs_listener is not None:
                    self.dcs_listener(specs, DataSource.NETWORK)

            def on_error_dcs(e: Exception):
                # pylint: disable=unused-argument
                pass

            self._network.listen_for_dcs(
                IStreamingListeners(on_error=on_error_dcs, on_update=on_update_dcs),
                lambda: self._network.get_dcs_fallback(
                    self._on_dcs_complete, since_time=self.last_update_time, log_on_exception=True
                ),
            )

        if self._network.is_pull_worker("download_id_lists"):
            if (
                    self._background_download_id_lists is None
                    or not self._background_download_id_lists.is_alive()
            ):
                self._spawn_bg_poll_id_lists()
        else:

            def on_update_id_list(id_lists: list, lcut: int):
                if self.last_update_time > lcut:
                    return
                if self.id_lists_listener is not None:
                    self.id_lists_listener(id_lists)

            def on_error_id_list(e: Exception):
                self._error_boundary.log_exception("_listen_for_id_list", e)

            self._network.listen_for_id_lists(
                IStreamingListeners(
                    on_error=on_error_id_list, on_update=on_update_id_list
                )
            )

    def _spawn_bg_poll_dcs(self):
        interval = self._options.rulesets_sync_interval or RULESETS_SYNC_INTERVAL
        fast_start = self._sync_failure_count > 0
        globals.logger.info(
            f"Starting polling for downloading config specs with an interval "
            f"of {interval}s")

        def sync_config_spec():
            for i, strategy in enumerate(self._config_sync_strategies):
                prev_failure_count = self._sync_failure_count
                self.get_config_spec(strategy)
                outof_sync = False
                time_elapsed = time.time() * 1000 - self.last_update_time
                if self._enforce_sync_fallback_threshold_in_ms is not None and time_elapsed > self._enforce_sync_fallback_threshold_in_ms:
                    outof_sync = True
                if prev_failure_count == self._sync_failure_count and not outof_sync:
                    globals.logger.log_process(
                        "Config Sync",
                        f"Syncing config values with {strategy.value}"
                        + (f"[{self.context.source_api}]" if self.context.source_api else "")
                        + " successful"
                    )
                    break
                if i < len(self._config_sync_strategies) - 1:
                    globals.logger.log_process(
                        "Config Sync",
                        f"Syncing config values failed with {strategy.value}"
                        + (f"[{self.context.source_api}]" if self.context.source_api else "")
                        + ", falling back to next available configured config sync method"
                    )

                else:
                    globals.logger.log_process(
                        "Config Sync",
                        f"Syncing config values failed with {strategy.value}"
                        + (f"[{self.context.source_api}]" if self.context.source_api else "")
                        + f". No more strategies left. The next sync will be in {interval} seconds."
                    )

        self._background_download_configs = spawn_background_thread(
            "bg_download_config_specs",
            self._sync,
            (sync_config_spec, interval, fast_start),
            self._error_boundary,
        )

    def _spawn_bg_poll_id_lists(self):
        interval = self._options.idlists_sync_interval or IDLISTS_SYNC_INTERVAL
        self._background_download_id_lists = spawn_background_thread(
            "bg_download_id_lists",
            self._sync,
            (self.download_id_lists, interval),
            self._error_boundary,
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

    def _get_sync_dcs_strategies(self) -> List[DataSource]:
        try:
            if self._options.config_sync_sources is not None:
                return self._options.config_sync_sources
            strategies = [DataSource.NETWORK]
            if (
                    self._options.data_store is not None
                    and self._options.data_store.should_be_used_for_querying_updates(
                STORAGE_ADAPTER_KEY
            )
            ):
                strategies = [DataSource.DATASTORE]
            if self._options.fallback_to_statsig_api:
                strategies.append(DataSource.STATSIG_NETWORK)
            return strategies
        except Exception:
            globals.logger.warning(
                "Failed to get sync sources, fallling back to always sync from statsig network "
            )
            return [DataSource.STATSIG_NETWORK]

    def shutdown(self):
        if self._background_download_configs is not None:
            self._background_download_configs.join(THREAD_JOIN_TIMEOUT)

        if self._background_download_id_lists is not None:
            self._background_download_id_lists.join(THREAD_JOIN_TIMEOUT)
