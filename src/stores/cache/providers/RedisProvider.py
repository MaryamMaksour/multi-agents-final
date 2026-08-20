from __future__ import annotations

import redis.asyncio as redis

from ..CacheInterface import CacheInterface


class RedisProvider(CacheInterface):

    def __init__(self, url: str):
        self.url = url
        self._client: "redis.Redis | None" = None

    def connect(self) -> "redis.Redis":
        if self._client is None:
            self._client = redis.from_url(self.url, decode_responses=True)
        return self._client

    def disconnect(self) -> None:
        self._client = None

    def get_client(self) -> "redis.Redis":
        return self.connect()
