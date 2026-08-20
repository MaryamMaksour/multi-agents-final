"""Postgres/pgvector connection pool.

Two things the legacy `main/conect_to_DB.py` got wrong and this fixes:

- `DB_COMMAND_TIMEOUT` was read from the environment and then never
  passed to `create_pool`, so a runaway query had no client-side bound
  at all.
- pgvector's asyncpg codec was imported but never registered, so vector
  values crossed the wire as text on every query.

`acquire()` is also the single place a principal can be pinned onto the
session, which is what row-level security policies key off. It is a
no-op until RLS_ENABLED is turned on and policies exist, but every SQL
path already routes through it, so enabling it later is a config change
rather than an audit of every call site.
"""
from __future__ import annotations

import contextlib
import logging
from typing import AsyncIterator, Optional

import asyncpg
from pgvector.asyncpg import register_vector

logger = logging.getLogger(__name__)


def _clean_host(host: str) -> str:
    """Tolerate a host accidentally written as a URL or with a port."""
    cleaned = (host or "").strip()
    cleaned = cleaned.replace("http://", "").replace("https://", "")
    if cleaned.count(":") == 1 and cleaned.split(":")[1].isdigit():
        cleaned = cleaned.split(":")[0]
    return cleaned


class PGClient:

    def __init__(self, config):
        self.config = config
        self._pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> asyncpg.Pool:
        if self._pool is not None:
            return self._pool

        host = _clean_host(self.config.PG_HOST)
        logger.info(
            "Connecting to Postgres host=%r port=%r db=%r user=%r ssl=%r",
            host, self.config.PG_PORT, self.config.PG_DBNAME,
            self.config.PG_USER, self.config.PG_SSL,
        )

        self._pool = await asyncpg.create_pool(
            host=host,
            port=int(self.config.PG_PORT),
            user=self.config.PG_USER,
            password=self.config.PG_PASSWORD,
            database=self.config.PG_DBNAME,
            ssl=self.config.PG_SSL if self.config.PG_SSL else None,
            min_size=self.config.DB_POOL_MIN,
            max_size=self.config.DB_POOL_MAX,
            command_timeout=self.config.DB_COMMAND_TIMEOUT,
            init=self._init_connection,
        )
        return self._pool

    async def disconnect(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    @staticmethod
    async def _init_connection(conn: asyncpg.Connection) -> None:
        # Registering the codec needs the pgvector extension to be
        # present. Tolerate its absence: vector values are only ever sent
        # as `$n::vector` literals and vector columns are never selected
        # back, so a missing codec degrades nothing - but letting the
        # exception through would make the whole pool fail to build.
        try:
            await register_vector(conn)
        except Exception:
            logger.warning("pgvector codec not registered (extension missing?)", exc_info=True)

    @contextlib.asynccontextmanager
    async def acquire(self, principal: Optional[str] = None) -> AsyncIterator[asyncpg.Connection]:
        """A pooled connection, optionally bound to an authenticated principal.

        With RLS_ENABLED, the connection is wrapped in a transaction and
        `app.user_id` is set for its lifetime, so row-level security
        policies decide what this user may read. Enforcement then lives
        in the database, where a prompt-injected query cannot reach it.
        """
        pool = await self.connect()
        async with pool.acquire() as conn:
            if self.config.RLS_ENABLED and principal:
                async with conn.transaction():
                    await conn.execute("SELECT set_config('app.user_id', $1, true)", principal)
                    yield conn
            else:
                yield conn

    async def apply_statement_timeout(self, conn: asyncpg.Connection) -> None:
        """Server-side ceiling, independent of the client-side timeout."""
        await conn.execute(f"SET LOCAL statement_timeout = {int(self.config.SQL_STATEMENT_TIMEOUT_MS)}")
