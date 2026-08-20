# stores/cache/vector_token_store.py
#
# A short-TTL Redis-backed handoff for embeddings between tool calls in
# the same turn: embed_query_tool mints a token, db_execute resolves it
# back to the vector when building its params. Was a plain process-global
# dict, invisible across FastAPI replicas - a token minted by one replica
# could never be resolved by another. These tokens only need to live for
# the duration of one turn's tool-calling loop, not forever.
from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from . import get_redis

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
