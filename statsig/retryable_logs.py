from dataclasses import dataclass

@dataclass
class RetryableLogs:
    payload: str
    retries: int = 0
