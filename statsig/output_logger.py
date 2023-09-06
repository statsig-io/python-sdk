from datetime import datetime
import logging
import sys


class OutputLogger:
    def __init__(self, name):
        self._disabled = 'unittest' in sys.modules
        self._logger = logging.getLogger(name)

    def log_process(self, process: str, msg: str):
        message = f"[{datetime.now().isoformat(' ')}] {process}: {msg}"
        self.info(message)

    def debug(self, msg, *args, **kwargs):
        if not self._disabled:
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
