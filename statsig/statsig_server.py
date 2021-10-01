from statsig.evaluator import _Evaluator
from .statsig_network import _StatsigNetwork
from .statsig_logger import _StatsigLogger
from .dynamic_config import DynamicConfig
from .statsig_options import StatsigOptions
from .version import __version__

class StatsigServer:
    def initialize(self, sdkKey, options = None):
        if options is None:
            options = StatsigOptions()

        self._network = _StatsigNetwork(sdkKey, options.api)
        self._logger = _StatsigLogger(self._network)
        self._evaluator = _Evaluator()

        specs = self._network.post_request("/download_config_specs", {})
        self._evaluator.setDownloadedConfigs(specs)

        self.__statsig_metadata = {
            "sdkVersion": __version__,
            "sdkType": "py-server"
        }

        self._initialized = True

    def check_gate(self, user, gate):
        if not self._initialized:
            raise RuntimeError('Must call initialize before checking gates/configs/experiments or logging events')
        if not user or not user.user_id:
            raise ValueError('A non-empty StatsigUser.user_id is required. See https://docs.statsig.com/messages/serverRequiredUserID')
        if not gate:
            return False
    
        result = self._evaluator.check_gate(user, gate)
        if result.fetch_from_server:
            network_gate = self._network.post_request("/check_gate", {
                "gateName": gate,
                "user": user.to_dict(),
                "statsigMetadata": self.__statsig_metadata,
            })
            if network_gate is None:
                return False
            
            return network_gate["value"]
        else:
            self._logger.log_gate_exposure(user, gate, result.boolean_value, result.rule_id)
        return result.boolean_value

    def get_config(self, user, config):
        if not self._initialized:
            raise RuntimeError('Must call initialize before checking gates/configs/experiments or logging events')
        if not user or not user.user_id:
            raise ValueError('A non-empty StatsigUser.user_id is required. See https://docs.statsig.com/messages/serverRequiredUserID')
        if not config:
            return DynamicConfig({})

        result = self._evaluator.get_config(user, config)
        if result.fetch_from_server:
            network_config = self._network.post_request("/get_config", {
                "configName": config,
                "user": user,
                "statsigMetadata": self._statsig_metadata,
            })
            if network_config is None:
                return DynamicConfig({}, config, "")
            
            return DynamicConfig(network_config["value"], config, network_config["ruleID"])
        else:
            self._logger.log_config_exposure(user, config, result.rule_id)
        return DynamicConfig(result.json_value, config, result.rule_id)
    
    def get_experiment(self, user, config):
        return self.get_config(user, config)

    def log_event(self, event):
        if not self._initialized:
            raise RuntimeError('Must call initialize before checking gates/configs/experiments or logging events')
    
        self._logger.log(event)
    
    def shutdown(self):
        self._logger.shutdown()