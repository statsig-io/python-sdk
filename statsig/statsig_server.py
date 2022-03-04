import asyncio
import json
import threading
from .evaluator import _ConfigEvaluation, _Evaluator
from .statsig_network import _StatsigNetwork
from .statsig_logger import _StatsigLogger
from .dynamic_config import DynamicConfig
from .statsig_options import StatsigOptions
from .version import __version__

RULESETS_SYNC_INTERVAL = 10
IDLISTS_SYNC_INTERVAL = 60


class StatsigServer:

    def initialize(self, sdkKey: str, options=None):
        if sdkKey is None or not sdkKey.startswith("secret-"):
            raise ValueError(
                'Invalid key provided.  You must use a Server Secret Key from the Statsig console.')
        if options is None:
            options = StatsigOptions()
        self._options = options
        self.__shutdown_event = threading.Event()
        self.__statsig_metadata = {
            "sdkVersion": __version__,
            "sdkType": "py-server"
        }
        self._network = _StatsigNetwork(sdkKey, options)
        self._logger = _StatsigLogger(
            self._network, self.__shutdown_event, self.__statsig_metadata, options.local_mode)
        self._evaluator = _Evaluator()

        self._last_update_time = 0

        if not options.local_mode:
            if options.bootstrap_values is not None:
                self._bootstrap_config_specs()
            else:
                self._download_config_specs()
            self.__background_download_configs = threading.Thread(
                target=self._sync, args=(self._download_config_specs, options.rulesets_sync_interval or RULESETS_SYNC_INTERVAL,))
            self.__background_download_configs.daemon = True
            self.__background_download_configs.start()

        if not options.local_mode:
            self._download_id_lists()
            self.__background_download_idlists = threading.Thread(
                target=self._sync, args=(self._download_id_lists, options.idlists_sync_interval or IDLISTS_SYNC_INTERVAL,))
            self.__background_download_idlists.daemon = True
            self.__background_download_idlists.start()

        self._initialized = True

    def check_gate(self, user: object, gate_name: str):
        if not self._initialized:
            raise RuntimeError(
                'Must call initialize before checking gates/configs/experiments or logging events')
        if not user or not user.user_id:
            raise ValueError(
                'A non-empty StatsigUser.user_id is required. See https://docs.statsig.com/messages/serverRequiredUserID')
        if not gate_name:
            return False
        result = self.__check_gate_server_fallback(user, gate_name)
        return result.boolean_value

    def get_config(self, user: object, config_name: str):
        if not self._initialized:
            raise RuntimeError(
                'Must call initialize before checking gates/configs/experiments or logging events')
        if not user or not user.user_id:
            raise ValueError(
                'A non-empty StatsigUser.user_id is required. See https://docs.statsig.com/messages/serverRequiredUserID')
        if not config_name:
            return DynamicConfig({})
        result = self.__get_config_server_fallback(user, config_name)
        return DynamicConfig(result.json_value, config_name, result.rule_id)

    def get_experiment(self, user: object, experiment_name: str):
        return self.get_config(user, experiment_name)

    def log_event(self, event: object):
        if not self._initialized:
            raise RuntimeError(
                'Must call initialize before checking gates/configs/experiments or logging events')

        event.user = self.__normalize_user(event.user)
        self._logger.log(event)

    def shutdown(self):
        self.__shutdown_event.set()
        self._logger.shutdown()
        if not self._options.local_mode:
            self.__background_download_configs.join()
            self.__background_download_idlists.join()

    def override_gate(self, gate: str, value: bool, user_id: str = None):
        self._evaluator.override_gate(gate, value, user_id)

    def override_config(self, config: str, value: object, user_id: str = None):
        self._evaluator.override_config(config, value, user_id)

    def override_experiment(self, experiment: str, value: object, user_id: str = None):
        self._evaluator.override_config(experiment, value, user_id)

    def evaluate_all(self, user: object):
        all_gates = dict()
        for gate in self._evaluator.get_all_gates():
            result = self.__check_gate_server_fallback(user, gate, False)
            all_gates[gate] = {
                "value": result.boolean_value,
                "rule_id": result.rule_id
            }

        all_configs = dict()
        for config in self._evaluator.get_all_configs():
            result = self.__get_config_server_fallback(user, config, False)
            all_configs[config] = {
                "value": result.json_value,
                "rule_id": result.rule_id
            }
        return dict({
            "feature_gates": all_gates,
            "dynamic_configs": all_configs
        })

    def __check_gate_server_fallback(self, user: object, gate_name: str, log_exposure=True):
        user = self.__normalize_user(user)
        result = self._evaluator.check_gate(user, gate_name)
        if result.fetch_from_server:
            network_gate = self._network.post_request("check_gate", {
                "gateName": gate_name,
                "user": user.to_dict(True),
                "statsigMetadata": self.__statsig_metadata,
            })
            if network_gate is None:
                return _ConfigEvaluation()
            return _ConfigEvaluation(boolean_value=network_gate.get("value"), rule_id=network_gate.get("rule_id"))
        elif log_exposure:
            self._logger.log_gate_exposure(
                user, gate_name, result.boolean_value, result.rule_id, result.secondary_exposures)
        return result

    def __get_config_server_fallback(self, user: object, config_name: str, log_exposure=True):
        user = self.__normalize_user(user)

        result = self._evaluator.get_config(user, config_name)
        if result.fetch_from_server:
            network_config = self._network.post_request("get_config", {
                "configName": config_name,
                "user": user,
                "statsigMetadata": self.__statsig_metadata,
            })
            if network_config is None:
                return _ConfigEvaluation()

            return _ConfigEvaluation(json_value=network_config.get("value", {}), rule_id=network_config.get("ruleID", ""))
        elif log_exposure:
            self._logger.log_config_exposure(
                user, config_name, result.rule_id, result.secondary_exposures)
        return result

    def __normalize_user(self, user):
        if self._options is not None and self._options._environment is not None:
            user._statsig_environment = self._options._environment
        return user

    def _sync(self, sync_func, interval):
        while True:
            if self.__shutdown_event.wait(interval):
                break
            sync_func()
    
    def _bootstrap_config_specs(self,):
        if self._options.bootstrap_values is None:
            return
        try:
            specs = json.loads(self._options.bootstrap_values)
            self.__save_json_config_specs(specs)
        except ValueError: 
            ## JSON deconding failed, just let background thread update rulesets
            return

    def __save_json_config_specs(self, specs, notify = False):
        if specs is None:
            return
        time = specs.get("time")
        if time is not None:
            self._last_update_time = time
        if specs.get("has_updates", False):
            self._evaluator.setDownloadedConfigs(specs)
            if callable(self._options.rules_updated_callback):
                self._options.rules_updated_callback(json.dumps(specs))

    def _download_config_specs(self):
        specs = self._network.post_request("download_config_specs", {
            "statsigMetadata": self.__statsig_metadata,
            "sinceTime": self._last_update_time,
        })
        self.__save_json_config_specs(specs, True)

    def _download_id_list(self, list_name, list):
        res = self._network.post_request("download_id_list", {
            "listName": list_name,
            "statsigMetadata": self.__statsig_metadata,
            "sinceTime": list.get("time", 0),
        })
        if res is None:
            return
        ids = list.get("ids", dict())
        for id in res.get("add_ids", []):
            ids[id] = True
        for id in res.get("remove_ids", []):
            if id in ids:
                del ids[id]
        new_time = res.get("time", 0)
        if new_time > list.get("time", 0):
            list["time"] = new_time

    def _download_id_lists(self):
        thread_pool = []
        id_lists = self._evaluator.getIDLists()
        for list_name, list in id_lists.items():
            thread = threading.Thread(
                target=self._download_id_list, args=(list_name, list, ))
            thread.daemon = True
            thread_pool.append(thread)
            thread.start()
        for thread in thread_pool:
            thread.join()
