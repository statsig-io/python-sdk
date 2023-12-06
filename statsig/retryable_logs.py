from dataclasses import dataclass

@dataclass
class RetryableLogs:
    payload: str
    headers: dict
    event_count: int
    retries: int = 0
