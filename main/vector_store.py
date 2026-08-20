
# main/vector_store.py
#
# Was a plain process-global dict handing embeddings between tool calls by
# token. Unbounded (no eviction), and invisible across FastAPI replicas -
# a vector token minted by embed_query_tool on one replica could never be
# resolved by db_execute running on another. Redis-backed with a short
# TTL: these tokens only need to live for the duration of one turn's
# tool-calling loop, not forever.
from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from .redis_client import get_redis

VECTOR_TTL_SECONDS = 300
_KEY_PREFIX = "vector_cache:"


async def store_vector(vec: Any) -> str:
    token = f"vec_{uuid.uuid4().hex[:12]}"
    r = get_redis()
    await r.set(_KEY_PREFIX + token, json.dumps(vec), ex=VECTOR_TTL_SECONDS)
    return token


async def get_vector(token: str) -> Optional[Any]:
    r = get_redis()
    raw = await r.get(_KEY_PREFIX + token)
    if raw is None:
        return None
    return json.loads(raw)
