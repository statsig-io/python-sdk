from typing import Optional


class IDataStore:
    def get(self, key: str) -> Optional[str]:
        return None

    def set(self, key: str, value: str):
        pass

    def shutdown(self):
        pass
