from typing import List


class IDataStore:
    def get(self, key: str) -> str | None:
        return None

    def set(self, key: str, value: str):
        pass

    def shutdown(self):
        pass
