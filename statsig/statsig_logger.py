import multiprocessing, time
from .statsig_event import StatsigEvent

_CONFIG_EXPOSURE_EVENT = "statsig::config_exposure"
_GATE_EXPOSURE_EVENT = "statsig::gate_exposure"

class _StatsigLogger:
    def __init__(self, net):
        self.__events = list()
        self.__net = net

        self.__background_flush = multiprocessing.Process(target=self._flush_interval)
        self.__background_flush.start()

    def _flush_interval(self):
        while True:
            self.__flush()
            time.sleep(10)

    def log(self, event):
        self.__events.append(event.to_dict())
        if len(self.__events) >= 500:
            self.__flush()
    
    def log_gate_exposure(self, user, gate, value, rule_id):
        event = StatsigEvent(user, _GATE_EXPOSURE_EVENT)
        event.metadata = {
            "gate": gate,
            "gateValue": value,
            "ruleID": rule_id,
        }
        self.log(event)


    def log_config_exposure(self, user, config, rule_id):
        event = StatsigEvent(user, _CONFIG_EXPOSURE_EVENT)
        event.metadata = {
            "config": config,
            "ruleID": rule_id,
        }
        self.log(event)

    def __flush(self):
        if len(self.__events) == 0:
            return
        events_copy = self.__events.copy()
        self.__events = list()
        self.__net.post_request("/log_event", {
            "events": events_copy,
        })
    
    def shutdown(self):
        self.__background_flush.terminate()
        self.__flush()