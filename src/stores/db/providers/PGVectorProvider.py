from __future__ import annotations

import logging
from typing import Optional

import asyncpg

from ..DBInterface import DBInterface

logger = logging.getLogger(__name__)


def _clean_host(host: str) -> str:
    # removes whitespace/newlines and common accidental prefixes
    h = (host or "").strip()
    h = h.replace("http://", "").replace("https://", "")
    # remove accidental port suffix like "192.168.4.51:5432"
    if ":" in h and h.count(":") == 1 and h.split(":")[1].isdigit():
        h = h.split(":")[0]
    return h


class PGVectorProvider(DBInterface):

    def __init__(self, host, port, dbname, user, password, ssl, pool_min, pool_max):
        self.host = host
        self.port = port
        self.dbname = dbname
        self.user = user
        self.password = password
        self.ssl = ssl
        self.pool_min = pool_min
        self.pool_max = pool_max
        self._pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> asyncpg.Pool:
        if self._pool is not None:
            return self._pool

        host = _clean_host(self.host)
        port = int(self.port)

        logger.info("Connecting to Postgres host=%r port=%r db=%r user=%r ssl=%r pool=%d..%d",
                    host, port, self.dbname, self.user, self.ssl, self.pool_min, self.pool_max)

        self._pool = await asyncpg.create_pool(
            host=host,
            port=port,
            user=self.user,
            password=self.password,
            database=self.dbname,
            ssl=self.ssl if self.ssl else None,
            min_size=self.pool_min,
            max_size=self.pool_max,
        )
        return self._pool

    async def disconnect(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def get_pool(self) -> asyncpg.Pool:
        return await self.connect()
