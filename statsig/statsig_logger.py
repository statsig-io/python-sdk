import threading
from .statsig_event import StatsigEvent

_CONFIG_EXPOSURE_EVENT = "statsig::config_exposure"
_GATE_EXPOSURE_EVENT = "statsig::gate_exposure"

class _StatsigLogger:
    def __init__(self, net, shutdown_event):
        self.__events = list()
        self.__net = net

        self.__background_flush = threading.Thread(target=self._periodic_flush, args=(shutdown_event,))
        self.__background_flush.start()

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
        self.__flush()
        self.__background_flush.join()

    def _periodic_flush(self, shutdown_event):
        while True:
            if shutdown_event.wait(60):
                break
            self.__flush()
    