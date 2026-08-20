"""Shared fixtures.

Everything here fakes the two things a test must not need: a live
Postgres and a live model. What is being tested is the code between
them - which SQL is allowed through, what the tools return, whether the
loop feeds tool results back - and all of that is deterministic.
"""
from __future__ import annotations

import contextlib
import os
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

os.environ.setdefault("LLM_API_URL", "http://llm.invalid/v1")
os.environ.setdefault("GENERATION_MODEL_ID", "test-model")
os.environ.setdefault("EMBEDDING_MODEL_ID", "test-embed")
os.environ.setdefault("PG_HOST", "pg.invalid")
os.environ.setdefault("PG_DBNAME", "test")
os.environ.setdefault("PG_USER", "test")
os.environ.setdefault("PG_PASSWORD", "test")
os.environ.setdefault("AGENT_ROLE", "sub_agent")
os.environ.setdefault("AGENT_DOMAIN", "hr")


@pytest.fixture
def settings():
    from helpers.config import get_settings
    return get_settings()


class FakeConnection:
    def __init__(self, log):
        self.log = log

    async def fetchval(self, sql, *args):
        self.log.append(("fetchval", sql, args))
        return 42

    async def fetch(self, sql, *args):
        self.log.append(("fetch", sql, args))
        if "DISTINCT" in sql:
            return [{"value": "EV"}, {"value": "EV Sales"}]
        return [{"id": 1, "name": "Sara"}, {"id": 2, "name": "Omar"}]

    async def execute(self, sql, *args):
        self.log.append(("execute", sql, args))


class FakePGClient:
    """Records every statement and every principal it was given."""

    def __init__(self):
        self.log = []
        self.principals = []

    @contextlib.asynccontextmanager
    async def acquire(self, principal=None):
        self.principals.append(principal)
        yield FakeConnection(self.log)

    def statements(self, kind):
        return [sql for k, sql, _ in self.log if k == kind]

    def arguments(self, kind):
        return [args for k, _, args in self.log if k == kind]


@pytest.fixture
def pg_client():
    return FakePGClient()


@pytest.fixture
def embed_text():
    async def _embed(text: str):
        return [0.1] * 8
    return _embed


@pytest.fixture
def hr_tools(settings, pg_client, embed_text):
    from stores.agents.specs import get_spec
    from stores.agents.tools import build_sql_toolset

    spec = get_spec("hr")
    tools = build_sql_toolset(
        allowed_tables=spec.tables,
        table_notes=spec.table_notes,
        pg_client=pg_client,
        embed_text=embed_text,
        config=settings,
        log_sql=None,
    )
    return {tool.name: tool for tool in tools}
