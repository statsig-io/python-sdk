import time
from typing import Optional

from .evaluation_details import DataSource


class InitContext:
    start_time: int
    success: bool
    error: Optional[Exception]
    source: DataSource
    store_populated: bool
    source_api: Optional[str]
    timed_out: bool

    def __init__(self):
        self.start_time = int(time.time() * 1000)
        self.success = False
        self.error = None
        self.source = DataSource.UNINITIALIZED
        self.store_populated = False
        self.source_api = None
        self.timed_out = False
