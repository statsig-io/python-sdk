from typing import Optional

from statsig import IDataStore

has_imported_redis = False
try:
    import redis
    has_imported_redis = True
except ImportError:
    pass


class RedisDataStore(IDataStore):
    _connection: redis.Redis

    def __init__(self, host: str, port: int, password: str):
        if not has_imported_redis:
            raise ImportError(
                "Failed to import redis, have you installed the redis dependency?")

        self._connection = redis.Redis(host=host, port=port, password=password)

    def get(self, key: str) -> Optional[str]:
        return self._connection.get(key)

    def set(self, key: str, value: str):
        self._connection.set(key, value)

    def shutdown(self):
        self._connection.shutdown()
