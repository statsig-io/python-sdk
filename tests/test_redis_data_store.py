import unittest
from unittest.mock import MagicMock, patch

from statsig.redis_data_store import RedisDataStore


class TestRedisDataStore(unittest.TestCase):
    @patch("statsig.redis_data_store.redis.Redis")
    def test_constructor_requests_decoded_responses(self, redis_cls):
        redis_cls.return_value = MagicMock()
        RedisDataStore("localhost", 6379, "secret")
        redis_cls.assert_called_once_with(
            host="localhost", port=6379, password="secret", decode_responses=True
        )

    @patch("statsig.redis_data_store.redis.Redis")
    def test_get_returns_string_payload(self, redis_cls):
        connection = MagicMock()
        connection.get.return_value = '{"dynamic_configs": []}'
        redis_cls.return_value = connection

        store = RedisDataStore("localhost", 6379, "secret")
        self.assertEqual(store.get("statsig.cache"), '{"dynamic_configs": []}')

    @patch("statsig.redis_data_store.redis.Redis")
    def test_set_stores_string_payload(self, redis_cls):
        connection = MagicMock()
        redis_cls.return_value = connection

        store = RedisDataStore("localhost", 6379, "secret")
        store.set("statsig.cache", "payload")
        connection.set.assert_called_once_with("statsig.cache", "payload")


if __name__ == "__main__":
    unittest.main()
