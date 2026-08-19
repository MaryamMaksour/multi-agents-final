
# main/redis_client.py
#
# App-level Redis client, separate from Celery's own broker/backend
# connection. Backs the conversation store and vector-token cache, both of
# which used to be plain process-global dicts - meaning the synchronous
# /chat path (FastAPI process) and the async /chat/async path (Celery
# worker process, which imports the service module fresh) silently had two
# independent copies of a session's history, and a vector token minted in
# one process was never visible to another.
from __future__ import annotations

import redis.asyncio as redis

from .config import REDIS_URL

_CLIENT: "redis.Redis | None" = None


def get_redis() -> "redis.Redis":
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = redis.from_url(REDIS_URL, decode_responses=True)
    return _CLIENT
