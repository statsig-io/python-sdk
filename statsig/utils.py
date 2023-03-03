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
    _capture_logs = False

    def __init__(self, name, level=logging.NOTSET):
        super().__init__(name=name, level=level)
        self.disabled = 'unittest' in sys.modules

    def log_process(self, process: str, msg: str):
        message = f"[{datetime.now().isoformat(' ')}] {process}: {msg}"
        super().info(message)
        self._append_log(process, message)

    def debug(self, msg, *args, **kwargs):
        self._append_log("debug", msg)
        super().debug(msg, *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        self._append_log("info", msg)
        super().info(msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        self._append_log("warning", msg)
        super().warning(msg, *args, **kwargs)

    def clear_log_history(self):
        self._logs = defaultdict(list)

    def _append_log(self, kind, msg):
        if self._capture_logs:
            self._logs[kind].append(msg)


logger = _OutputLogger("statsig.sdk")
