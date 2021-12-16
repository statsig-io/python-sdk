import asyncio
import threading
from .evaluator import _Evaluator
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
        self._logger = _StatsigLogger(self._network, self.__shutdown_event, self.__statsig_metadata, options.local_mode)
        self._evaluator = _Evaluator()
        
        self._last_update_time = 0
        
        if not options.local_mode:
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

    def check_gate(self, user, gate):
        if not self._initialized:
            raise RuntimeError(
                'Must call initialize before checking gates/configs/experiments or logging events')
        if not user or not user.user_id:
            raise ValueError(
                'A non-empty StatsigUser.user_id is required. See https://docs.statsig.com/messages/serverRequiredUserID')
        if not gate:
            return False
        user = self.__normalize_user(user)
        result = self._evaluator.check_gate(user, gate)
        if result.fetch_from_server:
            network_gate = self._network.post_request("check_gate", {
                "gateName": gate,
                "user": user.to_dict(True),
                "statsigMetadata": self.__statsig_metadata,
            })
            if network_gate is None:
                return False

            return network_gate.get("value", False)
        else:
            self._logger.log_gate_exposure(
                user, gate, result.boolean_value, result.rule_id, result.secondary_exposures)
        return result.boolean_value

    def get_config(self, user, config):
        if not self._initialized:
            raise RuntimeError(
                'Must call initialize before checking gates/configs/experiments or logging events')
        if not user or not user.user_id:
            raise ValueError(
                'A non-empty StatsigUser.user_id is required. See https://docs.statsig.com/messages/serverRequiredUserID')
        if not config:
            return DynamicConfig({})
        user = self.__normalize_user(user)

        result = self._evaluator.get_config(user, config)
        if result.fetch_from_server:
            network_config = self._network.post_request("get_config", {
                "configName": config,
                "user": user,
                "statsigMetadata": self.__statsig_metadata,
            })
            if network_config is None:
                return DynamicConfig({}, config, "")

            return DynamicConfig(network_config.get("value", {}), config, network_config.get("ruleID", ""))
        else:
            self._logger.log_config_exposure(
                user, config, result.rule_id, result.secondary_exposures)
        return DynamicConfig(result.json_value, config, result.rule_id)

    def get_experiment(self, user, config):
        return self.get_config(user, config)

    def log_event(self, event):
        if not self._initialized:
            raise RuntimeError(
                'Must call initialize before checking gates/configs/experiments or logging events')

        event.user = self.__normalize_user(event.user)
        self._logger.log(event)

    def shutdown(self):
        self.__shutdown_event.set()
        self._logger.shutdown()
        self.__background_download_configs.join()
        self.__background_download_idlists.join()

    def override_gate(self, gate:str, value:bool, user_id:str = None):
        self._evaluator.override_gate(gate, value, user_id)
    
    def override_config(self, config:str, value:object, user_id:str = None):
        self._evaluator.override_config(config, value, user_id)

    def override_experiment(self, experiment:str, value:object, user_id:str = None):
        self._evaluator.override_config(experiment, value, user_id)

    def __normalize_user(self, user):
        if self._options is not None and self._options._environment is not None:
            user._statsig_environment = self._options._environment
        return user

    def _sync(self, sync_func, interval):
        while True:
            if self.__shutdown_event.wait(interval):
                break
            sync_func()

    def _download_config_specs(self):
        specs = self._network.post_request("download_config_specs", {
            "statsigMetadata": self.__statsig_metadata,
            "sinceTime": self._last_update_time,
        })
        if specs is None:
            return
        time = specs.get("time")
        if time is not None:
            self._last_update_time = time
        if specs.get("has_updates", False):
            self._evaluator.setDownloadedConfigs(specs)

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
