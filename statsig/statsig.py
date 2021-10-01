from .statsig_server import StatsigServer

_instance = StatsigServer()

def initialize(secretKey, options = None):
    _instance.initialize(secretKey, options)

def check_gate(user, gate):
    return _instance.check_gate(user, gate)

def get_config(user, config):
    return _instance.get_config(user, config)

def get_experiment(user, experiment):
    return get_config(user, experiment)

def log_event(event):
    _instance.log_event(event)

def shutdown():
    _instance.shutdown()
