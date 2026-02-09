from typing import Optional


class InitializeDetails:
    duration: int
    source: str
    init_success: bool
    store_populated: bool
    error: Optional[Exception]
    timed_out: bool
    init_source_api: Optional[str]
    init_source_api_id_lists: Optional[str]
    fallback_spec_used: bool
    fallback_id_lists_used: bool

    def __init__(
        self,
        duration: int,
        source: str,
        init_success: bool,
        store_populated: bool,
        id_list_count: int,
        error: Optional[Exception],
        init_source_api: Optional[str] = None,
        timed_out: bool = False,
        init_source_api_id_lists: Optional[str] = None,
        fallback_spec_used: bool = False,
        fallback_id_lists_used: bool = False,
    ):
        self.duration = duration
        self.source = source
        self.init_success = init_success
        self.error = error
        self.store_populated = store_populated
        self.id_list_count = id_list_count
        self.init_source_api = init_source_api
        self.init_source_api_id_lists = init_source_api_id_lists
        self.fallback_spec_used = fallback_spec_used
        self.fallback_id_lists_used = fallback_id_lists_used
        self.timed_out = timed_out
