from collections import defaultdict
from datetime import datetime
from enum import Enum
from logging import Logger
import logging
import sys


def str_or_none(field):
    return str(field) if field is not None else None


def to_raw_value(value):
    if isinstance(value, Enum):
        return value.value
    return value


def to_raw_dict_or_none(field: dict):
    return {k: to_raw_value(v) for k, v in field.items()} if field is not None else None


class _OutputLogger(Logger):
    _logs = defaultdict(list)
    def __init__(self, name='statsig.sdk', level=logging.NOTSET):
        super().__init__(name=name, level=level)
        self.root.setLevel(level)

    def log_process(self, process: str, msg: str):
        message = f"[{datetime.now().isoformat(' ')}] {process}: {msg}"
        super().info(message)
        self._logs[process].append(message)

    def debug(self, msg, *args, **kwargs):
        self._logs["debug"].append(msg % args)
        super().debug(msg, *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        self._logs["info"].append(msg % args)
        super().info(msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        self._logs["warning"].append(msg % args)
        super().warning(msg, *args, **kwargs)

    def clear_log_history(self):
        self._logs = defaultdict(list)


logging.setLoggerClass(_OutputLogger)
logging.basicConfig()
logger = logging.getLogger('statsig.sdk')
logger.disabled = 'unittest' in sys.modules
