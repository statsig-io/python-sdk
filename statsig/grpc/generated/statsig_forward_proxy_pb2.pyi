from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class ConfigSpecRequest(_message.Message):
    __slots__ = ("sdkKey", "sinceTime")
    SDKKEY_FIELD_NUMBER: _ClassVar[int]
    SINCETIME_FIELD_NUMBER: _ClassVar[int]
    sdkKey: str
    sinceTime: int
    def __init__(self, sdkKey: _Optional[str] = ..., sinceTime: _Optional[int] = ...) -> None: ...

class ConfigSpecResponse(_message.Message):
    __slots__ = ("spec", "lastUpdated")
    SPEC_FIELD_NUMBER: _ClassVar[int]
    LASTUPDATED_FIELD_NUMBER: _ClassVar[int]
    spec: str
    lastUpdated: int
    def __init__(self, spec: _Optional[str] = ..., lastUpdated: _Optional[int] = ...) -> None: ...
