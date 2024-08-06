from typing import Dict, Optional, Union, Any


class _SDK_Configs:
    _flags: Dict[str, bool] = {}
    _configs: Dict[str, Any] = {}

    @staticmethod
    def set_flags(new_flags):
        _SDK_Configs._flags = new_flags

    @staticmethod
    def set_configs(new_configs):
        _SDK_Configs._configs = new_configs

    @staticmethod
    def on(key):
        return _SDK_Configs._flags.get(key, False) is True

    @staticmethod
    def get_config_num_value(config: str) -> Optional[Union[int, float]]:
        value = _SDK_Configs._configs.get(config)
        if isinstance(value, (int, float)):
            return value
        return None
