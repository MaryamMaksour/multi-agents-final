
# main/redis_client.py
#
# App-level Redis client. Backs the conversation store and vector-token
# cache, both of which used to be plain process-global dicts - meaning
# each FastAPI replica held its own independent copy of a session's
# history, and a vector token minted by one replica was never visible to
# another.
from __future__ import annotations

import redis.asyncio as redis

from .config import REDIS_URL

_CLIENT: "redis.Redis | None" = None


def get_redis() -> "redis.Redis":
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = redis.from_url(REDIS_URL, decode_responses=True)
    return _CLIENT
