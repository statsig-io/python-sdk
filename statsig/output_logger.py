import logging
import re
import sys
from enum import Enum


class LogLevel(Enum):
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    EXCEPTION = logging.ERROR


class OutputLogger:
    def __init__(self, name):
        self._disabled = 'unittest' in sys.modules
        self._logger = logging.getLogger(name)
        self._logger.setLevel(logging.WARNING)

    def _wrap_logging_method(self, log_method):
        """Wraps a logging method in a try-except block."""

        def wrapper(msg, *args, **kwargs):
            try:
                if not self._disabled:
                    sanitized_msg, sanitized_args, sanitized_kwargs = self._sanitize_args(msg, *args, **kwargs)
                    log_method(sanitized_msg, *sanitized_args, **sanitized_kwargs)
            except Exception:
                pass

        return wrapper

    def log_process(self, process: str, msg: str):
        self.debug(f"{process}: {msg}")

    def _sanitize_args(self, msg, *args, **kwargs):
        sanitized_msg = sanitize(msg)
        sanitized_args = tuple(sanitize(str(arg)) for arg in args)
        sanitized_kwargs = {k: sanitize(str(v)) for k, v in kwargs.items()}
        return sanitized_msg, sanitized_args, sanitized_kwargs

    def set_log_level(self, log_level: LogLevel):
        self._logger.setLevel(log_level.value)

    def debug(self, msg, *args, **kwargs):
        self._wrap_logging_method(self._logger.debug)(msg, *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        self._wrap_logging_method(self._logger.info)(msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        self._wrap_logging_method(self._logger.warning)(msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        self._wrap_logging_method(self._logger.error)(msg, *args, **kwargs)

    def exception(self, msg, *args, **kwargs):
        self._wrap_logging_method(self._logger.exception)(msg, *args, **kwargs)


def sanitize(string: str) -> str:
    key_pattern = re.compile(r'secret-[a-zA-Z0-9]+')
    return key_pattern.sub('secret-****', string)
