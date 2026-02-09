import time
from typing import Optional

from .evaluation_details import DataSource


class InitContext:
    start_time: int
    success: bool
    error: Optional[Exception]
    source: DataSource
    store_populated: bool
    id_list_count: int
    source_api: Optional[str]
    source_api_id_lists: Optional[str]
    fallback_spec_used: bool
    fallback_id_lists_used: bool
    timed_out: bool

    def __init__(self):
        self.start_time = int(time.time() * 1000)
        self.success = False
        self.error = None
        self.source = DataSource.UNINITIALIZED
        self.store_populated = False
        self.id_list_count = 0
        self.source_api = None
        self.source_api_id_lists = None
        self.fallback_spec_used = False
        self.fallback_id_lists_used = False
        self.timed_out = False
