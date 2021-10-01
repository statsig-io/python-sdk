import multiprocessing, time
from .statsig_event import StatsigEvent

_CONFIG_EXPOSURE_EVENT = "statsig::config_exposure"
_GATE_EXPOSURE_EVENT = "statsig::gate_exposure"

class StatsigLogger:
    def __init__(self, net):
        self.events = list()
        self.net = net

        self._background_flush = multiprocessing.Process(target=self._flush_interval)
        self._background_flush.start()

    def _flush_interval(self):
        while True:
            self.flush()
            time.sleep(10)

    def log(self, event):
        self.events.append(event.toJSON())
    
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

    def flush(self):
        if len(self.events) == 0:
            return
        events_copy = self.events.copy()
        self.events = list()
        self.net.post_request("/log_event", {
            "events": events_copy,
        })
    
    def shutdown(self):
        self._background_flush.terminate()
        self.flush()