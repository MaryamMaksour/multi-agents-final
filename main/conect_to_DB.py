
# main/conect_to_DB.py
from __future__ import annotations

import logging
from typing import Optional
import asyncpg
from pgvector.asyncpg import register_vector

from .config import PG_HOST, PG_PORT, PG_DBNAME, PG_USER, PG_PASSWORD, PG_SSL, DB_POOL_MIN, DB_POOL_MAX
import os

logger = logging.getLogger(__name__)





_POOL: Optional[asyncpg.Pool] = None


def _clean_host(host: str) -> str:
    # removes whitespace/newlines and common accidental prefixes
    h = (host or "").strip()
    h = h.replace("http://", "").replace("https://", "")
    # remove accidental port suffix like "192.168.4.51:5432"
    if ":" in h and h.count(":") == 1 and h.split(":")[1].isdigit():
        h = h.split(":")[0]
    return h


async def get_pool() -> asyncpg.Pool:
    global _POOL
    if _POOL is not None:
        return _POOL
    
    
    ''' logger.warning("CONFIG PG_HOST=%r PG_PORT=%r PG_DBNAME=%r PG_USER=%r PG_SSL=%r",
               PG_HOST, PG_PORT, PG_DBNAME, PG_USER, PG_SSL)

'''
    host = _clean_host(PG_HOST)
    port = int(PG_PORT)

    logger.info("Connecting to Postgres host=%r port=%r db=%r user=%r ssl=%r pool=%d..%d",
                host, port, PG_DBNAME, PG_USER, PG_SSL, DB_POOL_MIN, DB_POOL_MAX)

    _POOL = await asyncpg.create_pool(
        host=host,
        port=port,
        user=PG_USER,
        password=PG_PASSWORD,
        database=PG_DBNAME,
        ssl=PG_SSL if PG_SSL else None,
        min_size=DB_POOL_MIN,
        max_size=DB_POOL_MAX,
    )
    return _POOL


async def close_pool() -> None:
    global _POOL
    if _POOL is not None:
        await _POOL.close()
        _POOL = None
