import logging
import sys


class OutputLogger:
    def __init__(self, name, enable_debug_logs=False):
        self._disabled = 'unittest' in sys.modules
        self._logger = logging.getLogger(name)
        self._enable_debug_logs = enable_debug_logs

    def log_process(self, process: str, msg: str):
        message = f"{process}: {msg}"
        self.debug(message)

    def debug(self, msg, *args, **kwargs):
        if not self._disabled and self._enable_debug_logs:
            self._logger.debug(msg, *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        if not self._disabled:
            self._logger.info(msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        if not self._disabled:
            self._logger.warning(msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        if not self._disabled:
            self._logger.error(msg, *args, **kwargs)

    def exception(self, msg, *args, **kwargs):
        if not self._disabled:
            self._logger.exception(msg, *args, **kwargs)
