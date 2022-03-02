import threading
import queue
from .statsig_event import StatsigEvent

_CONFIG_EXPOSURE_EVENT = "statsig::config_exposure"
_GATE_EXPOSURE_EVENT = "statsig::gate_exposure"


class _StatsigLogger:
    def __init__(self, net, shutdown_event, statsig_metadata, local_mode):
        self.__events = list()
        self.__retry_logs = queue.Queue(maxsize=10)
        self.__net = net
        self.__statsig_metadata = statsig_metadata
        self.__local_mode = local_mode

        self.__background_flush = threading.Thread(
            target=self._periodic_flush, args=(shutdown_event,))
        self.__background_flush.daemon = True
        self.__background_flush.start()

        self.__background_retry = threading.Thread(
            target=self._periodic_retry, args=(shutdown_event,))
        self.__background_retry.daemon = True
        self.__background_retry.start()

    def log(self, event):
        if self.__local_mode:
            return
        self.__events.append(event.to_dict())
        if len(self.__events) >= 500:
            self.__flush()

    def log_gate_exposure(self, user, gate, value, rule_id, secondary_exposures):
        event = StatsigEvent(user, _GATE_EXPOSURE_EVENT)
        event.metadata = {
            "gate": gate,
            "gateValue": "true" if value else "false",
            "ruleID": rule_id,
        }
        if secondary_exposures is None:
            secondary_exposures = []
        event._secondary_exposures = secondary_exposures
        self.log(event)

    def log_config_exposure(self, user, config, rule_id, secondary_exposures):
        event = StatsigEvent(user, _CONFIG_EXPOSURE_EVENT)
        event.metadata = {
            "config": config,
            "ruleID": rule_id,
        }
        if secondary_exposures is None:
            secondary_exposures = []
        event._secondary_exposures = secondary_exposures
        self.log(event)

    def __flush(self):
        if len(self.__events) == 0:
            return
        events_copy = self.__events.copy()
        self.__events = list()
        res = self.__net.retryable_request("log_event", {
            "events": events_copy,
            "statsigMetadata": self.__statsig_metadata,
        })
        if res is not None:
            self.__retry_logs.put(res, False)

    def shutdown(self):
        self.__flush()
        self.__background_flush.join()

    def _periodic_flush(self, shutdown_event):
        while True:
            if shutdown_event.wait(60):
                break
            self.__flush()

    def _periodic_retry(self, shutdown_event):
        while True:
            if shutdown_event.wait(60):
                break
            for i in range(self.__retry_logs.qsize()):
                payload = self.__retry_logs.get()
                res = self.__net.retryable_request("log_event", payload)
                if res is not None:
                    self.__retry_logs.put(res)
                self.__retry_logs.task_done()
