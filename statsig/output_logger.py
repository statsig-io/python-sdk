import logging
import re
import sys


class OutputLogger:
    def __init__(self, name, enable_debug_logs=False):
        self._disabled = 'unittest' in sys.modules
        self._logger = logging.getLogger(name)
        self._enable_debug_logs = enable_debug_logs

    def log_process(self, process: str, msg: str):
        message = sanitize(f"{process}: {msg}")
        self.debug(message)

    def _sanitize_args(self, msg, *args, **kwargs):
        sanitized_msg = sanitize(msg)
        sanitized_args = tuple(sanitize(str(arg)) for arg in args)
        sanitized_kwargs = {k: sanitize(str(v)) for k, v in kwargs.items()}
        return sanitized_msg, sanitized_args, sanitized_kwargs

    def debug(self, msg, *args, **kwargs):
        sanitized_msg, sanitized_args, sanitized_kwargs = self._sanitize_args(msg, *args, **kwargs)
        if not self._disabled and self._enable_debug_logs:
            self._logger.debug(sanitized_msg, *sanitized_args, **sanitized_kwargs)

    def info(self, msg, *args, **kwargs):
        sanitized_msg, sanitized_args, sanitized_kwargs = self._sanitize_args(msg, *args, **kwargs)
        if not self._disabled:
            self._logger.info(sanitized_msg, *sanitized_args, **sanitized_kwargs)

    def warning(self, msg, *args, **kwargs):
        sanitized_msg, sanitized_args, sanitized_kwargs = self._sanitize_args(msg, *args, **kwargs)
        if not self._disabled:
            self._logger.warning(sanitized_msg, *sanitized_args, **sanitized_kwargs)

    def error(self, msg, *args, **kwargs):
        sanitized_msg, sanitized_args, sanitized_kwargs = self._sanitize_args(msg, *args, **kwargs)
        if not self._disabled:
            self._logger.error(sanitized_msg, *sanitized_args, **sanitized_kwargs)

    def exception(self, msg, *args, **kwargs):
        sanitized_msg, sanitized_args, sanitized_kwargs = self._sanitize_args(msg, *args, **kwargs)
        if not self._disabled:
            self._logger.exception(sanitized_msg, *sanitized_args, **sanitized_kwargs)


def sanitize(string: str) -> str:
    key_pattern = re.compile(r'secret-[a-zA-Z0-9]+')
    return key_pattern.sub('secret-****', string)
