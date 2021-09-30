
class StatsigLogger:
    def __init__(self, net):
        print('StatsigLogger')
        self.events = list()
        self.net = net

    def log(self, event):
        self.events.append(event.toJSON())

    def flush(self):
        events_copy = self.events.copy()
        self.events = list()
        self.net.post_request("/log_event", {
            "events": events_copy,
        })