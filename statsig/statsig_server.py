import threading
from .evaluator import _Evaluator
from .statsig_network import _StatsigNetwork
from .statsig_logger import _StatsigLogger
from .dynamic_config import DynamicConfig
from .statsig_options import StatsigOptions
from .version import __version__

class StatsigServer:
    def initialize(self, sdkKey:str, options = None):
        if sdkKey is None or not sdkKey.startswith("secret-"):
            raise ValueError('Invalid key provided.  You must use a Server Secret Key from the Statsig console.')
        if options is None:
            options = StatsigOptions()
        self._options = options
        self.__shutdown_event = threading.Event()
        self._network = _StatsigNetwork(sdkKey, options.api)
        self._logger = _StatsigLogger(self._network, self.__shutdown_event)
        self._evaluator = _Evaluator()
        self.__statsig_metadata = {
            "sdkVersion": __version__,
            "sdkType": "py-server"
        }
        self._last_update_time = 0

        self._download_config_specs()

        self.__background_download = threading.Thread(target=self._update_specs)
        self.__background_download.start()

        self._initialized = True

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

    def _update_specs(self):
        while True:
            if self.__shutdown_event.wait(10):
                break
            self._download_config_specs()

    def check_gate(self, user, gate):
        if not self._initialized:
            raise RuntimeError('Must call initialize before checking gates/configs/experiments or logging events')
        if not user or not user.user_id:
            raise ValueError('A non-empty StatsigUser.user_id is required. See https://docs.statsig.com/messages/serverRequiredUserID')
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
            self._logger.log_gate_exposure(user, gate, result.boolean_value, result.rule_id, result.secondary_exposures)
        return result.boolean_value

    def get_config(self, user, config):
        if not self._initialized:
            raise RuntimeError('Must call initialize before checking gates/configs/experiments or logging events')
        if not user or not user.user_id:
            raise ValueError('A non-empty StatsigUser.user_id is required. See https://docs.statsig.com/messages/serverRequiredUserID')
        if not config:
            return DynamicConfig({})
        user = self.__normalize_user(user)

        result = self._evaluator.get_config(user, config)
        if result.fetch_from_server:
            network_config = self._network.post_request("get_config", {
                "configName": config,
                "user": user,
                "statsigMetadata": self._statsig_metadata,
            })
            if network_config is None:
                return DynamicConfig({}, config, "")
            
            return DynamicConfig(network_config.get("value", {}), config, network_config.get("ruleID", ""))
        else:
            self._logger.log_config_exposure(user, config, result.rule_id, result.secondary_exposures)
        return DynamicConfig(result.json_value, config, result.rule_id)
    
    def get_experiment(self, user, config):
        return self.get_config(user, config)

    def log_event(self, event):
        if not self._initialized:
            raise RuntimeError('Must call initialize before checking gates/configs/experiments or logging events')
    
        event.user = self.__normalize_user(event.user)
        self._logger.log(event)
    
    def shutdown(self):
        self.__shutdown_event.set()
        self._logger.shutdown()
        self.__background_download.join()

    def __normalize_user(self, user):
        if self._options is not None and self._options._environment is not None:
            user._statsig_environment = self._options._environment
        return user