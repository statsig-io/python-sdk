import hashlib
import json
from enum import Enum
from struct import unpack
from typing import Optional, Dict, Any


class HashingAlgorithm(Enum):
    SHA256 = 'sha256'
    DJB2 = 'djb2'
    NONE = 'none'


def str_or_none(field):
    return str(field) if field is not None else None


def to_raw_value(value):
    if isinstance(value, Enum):
        return value.value
    return value


def to_raw_dict_or_none(field: Optional[dict]):
    return {k: to_raw_value(v) for k, v in field.items()} if field is not None else None


def fasthash(value: str):
    hash = 0
    for (_i, c) in enumerate(value):
        hash = (hash << 5) - hash + ord(c)
        hash = hash & hash
    return hash & 0xffffffff


def djb2_hash(value: str):
    return str(fasthash(value))


def djb2_hash_for_dict(object: dict):
    return djb2_hash(json.dumps(get_sorted_dict(object), separators=(',', ':')))


def get_sorted_dict(object: dict):
    return {k: get_sorted_dict(object[k]) if isinstance(object[k], dict) else object[k] for k in sorted(object.keys())}


def get_or_default(val: Optional[Any], default: Any):
    if val is None:
        return default
    return val


def sha256_hash(key: str) -> int:
    return unpack('>Q', hashlib.sha256(str(key).encode('utf-8')).digest()[:8])[0]


# Constants
TWO_TO_THE_63 = 1 << 63
TWO_TO_THE_64 = 1 << 64


def bigquery_hash(string: str) -> int:
    num = sha256_hash(string)
    if num >= TWO_TO_THE_63:
        return num - TWO_TO_THE_64
    return num


def is_hash_in_sampling_rate(key: str, sampling_rate: int) -> bool:
    return bigquery_hash(key) % sampling_rate == 0


def compute_dedupe_key_for_gate(
        gate_name: str,
        rule_id: str,
        value: bool,
        user_id: Optional[str],
        custom_ids: Optional[Dict[str, str]],
) -> str:
    user_key = compute_user_key(user_id, custom_ids)
    exposure_key = f"n:{gate_name};u:{user_key}r:{rule_id};v:{value}"
    return exposure_key


def compute_dedupe_key_for_config(
        config_name: str,
        rule_id: str,
        user_id: Optional[str],
        custom_ids: Optional[Dict[str, str]],
) -> str:
    user_key = compute_user_key(user_id, custom_ids)
    exposure_key = f"n:{config_name};u:{user_key}r:{rule_id}"
    return exposure_key


def compute_dedupe_key_for_layer(
        layer_name: str,
        experiment_name: str,
        parameter_name: str,
        rule_id: str,
        user_id: Optional[str],
        custom_ids: Optional[Dict[str, str]],
) -> str:
    user_key = compute_user_key(user_id, custom_ids)
    exposure_key = f"n:{layer_name};e:{experiment_name};p:{parameter_name};u:{user_key}r:{rule_id}"
    return exposure_key


def compute_user_key(user_id: Optional[str], custom_ids: Optional[Dict[str, str]]) -> str:
    user_key = f"u:{user_id};"

    if custom_ids is not None:
        for k, v in custom_ids.items():
            user_key += f"{k}:{v};"

    return user_key
