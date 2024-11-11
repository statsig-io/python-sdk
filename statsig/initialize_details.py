from typing import Optional


class InitializeDetails:
    duration: int
    source: str
    init_success: bool
    store_populated: bool
    error: Optional[Exception]
    timed_out: bool
    init_source_api: Optional[str]

    def __init__(self, duration: int, source: str, init_success: bool, store_populated: bool,
                 error: Optional[Exception], init_source_api: Optional[str] = None, timed_out: bool = False):
        self.duration = duration
        self.source = source
        self.init_success = init_success
        self.error = error
        self.store_populated = store_populated
        self.init_source_api = init_source_api
        self.timed_out = timed_out
