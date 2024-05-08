from typing import Dict


class _SDKFlags:
    _flags: Dict[str, bool] = {}

    @staticmethod
    def set_flags(new_flags):
        _SDKFlags._flags = new_flags

    @staticmethod
    def on(key):
        return _SDKFlags._flags.get(key, False) is True
