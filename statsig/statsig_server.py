from statsig.evaluator import Evaluator
from .statsig_network import StatsigNetwork
from .statsig_logger import StatsigLogger
from .statsig_event import StatsigEvent
from .dynamic_config import DynamicConfig
from .statsig_options import StatsigOptions
from .version import __version__

class StatsigServer:
    def __init__(self):
        print("StatsigServer")
    
    def initialize(self, sdkKey, options = None):
        self.sdk_key = sdkKey
        if options is None:
            options = StatsigOptions()
        self.options = options

        self.network = StatsigNetwork(sdkKey, options.api)
        self.logger = StatsigLogger(self.network)
        self.evaluator = Evaluator()
        self.initialized = True

    def check_gate(self, user, gate):
        if not self.initialized:
            raise RuntimeError('Must call initialize before checking gates/configs/experiments or logging events')
        if not user or not user.user_id:
            raise ValueError('A non-empty StatsigUser.user_id is required. See https://docs.statsig.com/messages/serverRequiredUserID')
        if not gate:
            return False
    
        result = self.evaluator.check_gate(user, gate)
        return result.boolean_value

    def get_config(self, user, config):
        if not self.initialized:
            raise RuntimeError('Must call initialize before checking gates/configs/experiments or logging events')
        if not user or not user.user_id:
            raise ValueError('A non-empty StatsigUser.user_id is required. See https://docs.statsig.com/messages/serverRequiredUserID')
        if not config:
            return DynamicConfig({})

        result = self.evaluator.get_config(user, config)
        return DynamicConfig(result.json_value, config, result.rule_id)
        
    
    def get_experiment(self, user, config):
        return self.get_config()

    def log_event(self, event):
        if not self.initialized:
            raise RuntimeError('Must call initialize before checking gates/configs/experiments or logging events')
    
        self.logger.log(event)
    
    def shutdown(self):
        self.logger.flush()