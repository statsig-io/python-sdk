"""Redact server keys from SDK-generated diagnostic data."""
import re
from urllib.parse import quote, quote_plus

import grpc


class _RedactedRpcError(grpc.RpcError):
    def __init__(self, message, status, details):
        super().__init__(message)
        self._redacted_status = status
        self._redacted_details = details

    def code(self):
        return self._redacted_status

    def details(self):
        return self._redacted_details

_DCS_PATH = re.compile(r'(/download_config_specs/)[^/?\s"\']+', re.IGNORECASE)


def redact_text(value, key):
    text = str(value)
    if key:
        variants = (key, quote(key, safe=""), quote_plus(key, safe=""))
        for variant in sorted(set(variants), key=len, reverse=True):
            if variant:
                text = text.replace(variant, "[REDACTED]")
                if "%" in variant:
                    text = re.sub(re.escape(variant), "[REDACTED]", text, flags=re.IGNORECASE)
    return _DCS_PATH.sub(lambda m: m.group(1) + "[REDACTED]" + (".json" if m.group(0).endswith(".json") else ""), text)


def redact_exception(error, key):
    """Return a fresh exception without raw request fields, causes or traceback."""
    message = redact_text(error, key)
    if isinstance(error, grpc.RpcError):
        try:
            status = error.code()
        except Exception:
            status = None
        try:
            details = redact_text(error.details(), key)
        except Exception:
            details = message
        safe = _RedactedRpcError(message, status, details)
    else:
        try:
            safe = type(error)(message)
        except Exception:
            safe = RuntimeError(message)
    safe.__cause__ = None
    safe.__context__ = None
    safe.__traceback__ = None
    return safe


def redact_data(value, key):
    if isinstance(value, str):
        return redact_text(value, key)
    if isinstance(value, dict):
        return {redact_text(k, key) if isinstance(k, str) else k: redact_data(v, key) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_data(v, key) for v in value]
    if isinstance(value, tuple):
        return tuple(redact_data(v, key) for v in value)
    return value
