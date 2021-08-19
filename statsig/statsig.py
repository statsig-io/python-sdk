from ctypes import *
from os import path
from .dynamic_config import DynamicConfig
from .statsig_options import StatsigOptions
from .version import __version__

lib = cdll.LoadLibrary(path.join(path.abspath(path.dirname(__file__)), 'shared', 'statsig.so'))

class GoString(Structure):
    _fields_ = [("p", c_char_p), ("n", c_longlong)]

lib.Initialize.argtypes = [GoString, GoString, GoString, GoString]
lib.CheckGate.argtypes = [GoString, GoString]
lib.GetConfig.argtypes = [GoString, GoString]
lib.GetConfig.restype = c_char_p
lib.Shutdown.argtypes = []
lib.LogEvent.argtypes = [GoString]

name = "python-server"

initialized = False

def initialize(secretKey, options = None):
    if not secretKey or not secretKey.startswith('secret-'):
        raise ValueError('Invalid sdk key provided.  Please use a secret key from your project in the statsig console.')

    if options is None:
        options = StatsigOptions()
        options.api = 'https://api.statsig.com/v1'
    
    key = GoString(secretKey.encode('utf-8'), len(secretKey))
    opt_json = options.to_json_string()
    opt = GoString(opt_json.encode('utf-8'), len(opt_json))
    sdk_name = GoString(name.encode('utf-8'), len(name))
    sdk_version = GoString(__version__.encode('utf-8'), len(__version__))
    lib.Initialize(key, opt, sdk_name, sdk_version)
    global initialized
    initialized = True

def check_gate(user, gate):
    if not initialized:
        raise RuntimeError('Must call initialize before checking gates/configs/experiments or logging events')
    if not user or not user.user_id:
        raise ValueError('A non-empty StatsigUser.user_id is required. See https://docs.statsig.com/messages/serverRequiredUserID')
    if not gate:
        return False
    user_str = user.to_json_string()
    user_string = GoString(user_str.encode('utf-8'), len(user_str))
    gate_name = GoString(gate.encode('utf-8'), len(gate))
    return lib.CheckGate(user_string, gate_name) == 1

def get_config(user, config):
    if not initialized:
        raise RuntimeError('Must call initialize before checking gates/configs/experiments or logging events')
    if not user or not user.user_id:
        raise ValueError('A non-empty StatsigUser.user_id is required. See https://docs.statsig.com/messages/serverRequiredUserID')
    if not config:
        return DynamicConfig({})
    user_str = user.to_json_string()
    user_string = GoString(user_str.encode('utf-8'), len(user_str))
    config_name = GoString(config.encode('utf-8'), len(config))
    config = lib.GetConfig(user_string, config_name)

    return DynamicConfig(config.decode("utf-8"))

def get_experiment(user, experiment):
    return get_config(user, experiment)

def shutdown():
    lib.Shutdown()

def log_event(event):
    if not initialized:
        raise RuntimeError('Must call initialize before checking gates/configs/experiments or logging events')
    evt_str = event.to_json_string()
    lib.LogEvent(GoString(evt_str.encode('utf-8'), len(evt_str)))
