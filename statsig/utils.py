from enum import Enum
import json
from typing import Optional


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
