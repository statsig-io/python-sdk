from dataclasses import dataclass
from typing import Optional, Any, Dict, Union

from requests.structures import CaseInsensitiveDict


@dataclass
class RequestResult:
    data: Optional[Dict[str, Any]]
    success: bool
    status_code: Optional[int]
    text: Optional[str] = None
    headers: Optional[Union[CaseInsensitiveDict, Dict[str, str]]] = None
    error: Optional[Exception] = None
    retryable: bool = False
