from enum import Enum
from logging import Logger


def str_or_none(field):
    return str(field) if field is not None else None


def to_raw_value(value):
    if isinstance(value, Enum):
        return value.value
    return value


def to_raw_dict_or_none(field: dict):
    return {k: to_raw_value(v) for k, v in field.items()} if field is not None else None


class _OutputLogger(Logger):
    def __init__(self, name='statsig.sdk', level='INFO'):
        super().__init__(name=name, level=level)

    def log_process(self, process: str, msg: str, progress=None):
        progress = f" ({progress})" if progress is not None else ""
        self.info("[{datetime.now().isoformat(' ')}] %s%s: %s", process, progress, msg)


logger = _OutputLogger('statsig.sdk')
