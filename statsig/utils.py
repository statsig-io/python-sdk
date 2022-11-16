from enum import Enum


def str_or_none(field):
    return str(field) if field is not None else None


def to_raw_value(value):
    if isinstance(value, Enum):
        return value.value
    return value


def to_raw_dict_or_none(field: dict):
    return {k: to_raw_value(v) for k, v in field.items()} if field is not None else None
