from statsig.evaluator import Evaluator
from .statsig_network import StatsigNetwork
from .statsig_logger import StatsigLogger
from .statsig_event import StatsigEvent
from .dynamic_config import DynamicConfig
from .statsig_options import StatsigOptions
from .version import __version__

class StatsigServer:
    def initialize(self, sdkKey, options = None):
        self.sdk_key = sdkKey
        if options is None:
            options = StatsigOptions()
        self.options = options

        self.network = StatsigNetwork(sdkKey, options.api)
        self.logger = StatsigLogger(self.network)
        self.evaluator = Evaluator()

        specs = self.network.post_request("/download_config_specs", {})
        self.evaluator.setDownloadedConfigs(specs)

        self._statsig_metadata = {
            "sdkVersion": __version__,
            "sdkType": "py-server"
        }

        self.initialized = True

    def check_gate(self, user, gate):
        if not self.initialized:
            raise RuntimeError('Must call initialize before checking gates/configs/experiments or logging events')
        if not user or not user.user_id:
            raise ValueError('A non-empty StatsigUser.user_id is required. See https://docs.statsig.com/messages/serverRequiredUserID')
        if not gate:
            return False
    
        result = self.evaluator.check_gate(user, gate)
        if result.fetch_from_server:
            network_gate = self.network.post_request("/check_gate", {
                "gateName": gate,
                "user": user.to_dict(),
                "statsigMetadata": self._statsig_metadata,
            })
            if network_gate is None:
                return False
            
            return network_gate["value"]
        else:
            self.logger.log_gate_exposure(user, gate, result.boolean_value, result.rule_id)
        return result.boolean_value

    def get_config(self, user, config):
        if not self.initialized:
            raise RuntimeError('Must call initialize before checking gates/configs/experiments or logging events')
        if not user or not user.user_id:
            raise ValueError('A non-empty StatsigUser.user_id is required. See https://docs.statsig.com/messages/serverRequiredUserID')
        if not config:
            return DynamicConfig({})

        result = self.evaluator.get_config(user, config)
        if result.fetch_from_server:
            network_config = self.network.post_request("/get_config", {
                "configName": config,
                "user": user,
                "statsigMetadata": self._statsig_metadata,
            })
            if network_config is None:
                return DynamicConfig({}, config, "")
            
            return DynamicConfig(network_config["value"], config, network_config["ruleID"])
        else:
            self.logger.log_config_exposure(user, config, result.rule_id)
        return DynamicConfig(result.json_value, config, result.rule_id)
    
    def get_experiment(self, user, config):
        return self.get_config(user, config)

    def log_event(self, event):
        if not self.initialized:
            raise RuntimeError('Must call initialize before checking gates/configs/experiments or logging events')
    
        self.logger.log(event)
    
    def shutdown(self):
        self.logger.shutdown()