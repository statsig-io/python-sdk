import logging
import re
import sys
from enum import IntEnum


class LogLevel(IntEnum):
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    EXCEPTION = 50


LOG_COLORS = {
    LogLevel.DEBUG: "\033[90m",
    LogLevel.INFO: "\033[94m",
    LogLevel.WARNING: "\033[33m",
    LogLevel.ERROR: "\033[91m",
    LogLevel.EXCEPTION: "\033[95m"
}
RESET_COLOR = "\033[0m"


class OutputLogger:
    def __init__(self, name):
        self._disabled = 'unittest' in sys.modules
        self._logger = logging.getLogger(name)

        self._log_level = LogLevel.INFO

        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(self._CustomFormatter())
        self._logger.addHandler(handler)
        self._logger.setLevel(logging.DEBUG)  # We are overwriting this with our debug level

    class _CustomFormatter(logging.Formatter):
        def format(self, record):
            log_level = LogLevel[record.levelname] if record.levelname in LogLevel.__members__ else LogLevel.DEBUG
            color = LOG_COLORS.get(log_level, LOG_COLORS[LogLevel.DEBUG])
            message = super().format(record)
            return f"{color}{message}{RESET_COLOR}"

    def log_process(self, process: str, msg: str):
        self.debug(f"{process}: {msg}")

    def _sanitize_args(self, msg, *args, **kwargs):
        sanitized_msg = sanitize(msg)
        sanitized_args = tuple(sanitize(str(arg)) for arg in args)
        sanitized_kwargs = {k: sanitize(str(v)) for k, v in kwargs.items()}
        return sanitized_msg, sanitized_args, sanitized_kwargs

    def set_log_level(self, log_level: LogLevel):
        self._log_level = log_level

    def debug(self, msg, *args, **kwargs):
        if self._log_level <= LogLevel.DEBUG and not self._disabled:
            sanitized_msg, sanitized_args, sanitized_kwargs = self._sanitize_args(msg, *args, **kwargs)
            self._logger.debug(sanitized_msg, *sanitized_args, **sanitized_kwargs)

    def info(self, msg, *args, **kwargs):
        if self._log_level <= LogLevel.INFO and not self._disabled:
            sanitized_msg, sanitized_args, sanitized_kwargs = self._sanitize_args(msg, *args, **kwargs)
            self._logger.info(sanitized_msg, *sanitized_args, **sanitized_kwargs)

    def warning(self, msg, *args, **kwargs):
        if self._log_level <= LogLevel.WARNING and not self._disabled:
            sanitized_msg, sanitized_args, sanitized_kwargs = self._sanitize_args(msg, *args, **kwargs)
            self._logger.warning(sanitized_msg, *sanitized_args, **sanitized_kwargs)

    def error(self, msg, *args, **kwargs):
        if self._log_level <= LogLevel.ERROR and not self._disabled:
            sanitized_msg, sanitized_args, sanitized_kwargs = self._sanitize_args(msg, *args, **kwargs)
            self._logger.error(sanitized_msg, *sanitized_args, **sanitized_kwargs)

    def exception(self, msg, *args, **kwargs):
        if self._log_level <= LogLevel.EXCEPTION and not self._disabled:
            sanitized_msg, sanitized_args, sanitized_kwargs = self._sanitize_args(msg, *args, **kwargs)
            self._logger.exception(sanitized_msg, *sanitized_args, **sanitized_kwargs)


def sanitize(string: str) -> str:
    key_pattern = re.compile(r'secret-[a-zA-Z0-9]+')
    return key_pattern.sub('secret-****', string)
