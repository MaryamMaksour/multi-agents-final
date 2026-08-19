# agent_common/history_repo.py
#
# Every sub-agent service used a byte-for-byte identical implementation of
# this file before, differing only in one hardcoded table name
# (history1..history6). build_history_repo() is that same implementation,
# parameterized by table_name instead of copy-pasted per service.
from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence, Union

from main.conect_to_DB import get_pool
from main.embeddings import embed_query_async

logger = logging.getLogger(__name__)

EVENT_USER = "user"
EVENT_TOOL = "tool"
EVENT_SQL = "sql"
EVENT_ASSISTANT_FINAL = "assistant_final"
EVENT_PIPELINE = "pipeline"

_VALID_TABLE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def new_turn_id() -> str:
    """Create a new turn_id (UUID string) to correlate events across one user request."""
    return str(uuid.uuid4())


def _json_dumps(obj: Any) -> str:
    """Safe JSON dumps (handles non-serializable objects by stringifying)."""
    def default(o: Any):
        try:
            return str(o)
        except Exception:
            return "<non-serializable>"

    return json.dumps(obj, ensure_ascii=False, default=default)


@dataclass
class HistoryRepo:
    table_name: str
    new_turn_id: Callable[[], str]
    ensure_history_schema: Callable[[], Awaitable[None]]
    log_user_message: Callable[..., Awaitable[None]]
    log_assistant_final: Callable[..., Awaitable[None]]
    log_tool_call: Callable[..., Awaitable[None]]
    log_sql_query: Callable[..., Awaitable[None]]
    log_pipeline: Callable[..., Awaitable[None]]
    get_session_history: Callable[..., Awaitable[List[Dict[str, Any]]]]
    get_turn_history: Callable[..., Awaitable[List[Dict[str, Any]]]]
    delete_session_history: Callable[..., Awaitable[None]]
    get_memory: Callable[[str], Awaitable[list]]


def build_history_repo(table_name: str) -> HistoryRepo:
    """Builds the per-domain history-logging API bound to `table_name`."""
    if not _VALID_TABLE_NAME.match(table_name):
        raise ValueError(f"Invalid table name: {table_name!r}")

    create_table_sql = f"""
    CREATE TABLE IF NOT EXISTS {table_name} (
      id BIGSERIAL PRIMARY KEY,
      session_id TEXT NOT NULL,
      turn_id UUID NOT NULL,
      event_type TEXT NOT NULL,          -- 'user' | 'tool' | 'sql' | 'assistant_final'
      payload JSONB NOT NULL DEFAULT '{{}}'::jsonb,
      time  text,
      valid boolean,
      embed_user_query vector(1024),
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE INDEX IF NOT EXISTS idx_{table_name}_session_created
    ON {table_name}(session_id, created_at);

    CREATE INDEX IF NOT EXISTS idx_{table_name}_session_turn
    ON {table_name}(session_id, turn_id);

    CREATE INDEX IF NOT EXISTS idx_{table_name}_event_type
    ON {table_name}(event_type);
    """

    async def ensure_history_schema() -> None:
        """Ensures the history table exists. Call once at startup."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(create_table_sql)
        logger.info("History schema ensured (table: %s).", table_name)

    async def _insert_event(
        session_id: str,
        turn_id: Union[str, uuid.UUID],
        event_type: str,
        payload: Dict[str, Any],
        user_query: Optional[str] = None,
        time: Optional[str] = None,
    ) -> None:
        pool = await get_pool()
        turn_uuid = uuid.UUID(turn_id) if isinstance(turn_id, str) else turn_id

        if event_type == "user":
            embed_user_query = await embed_query_async(user_query)
            sql = f"""
            INSERT INTO {table_name} (session_id, turn_id, event_type, payload, embed_user_query)
            VALUES ($1, $2, $3, $4::jsonb, $5::vector)
            """
            async with pool.acquire() as conn:
                await conn.execute(sql, session_id, turn_uuid, event_type, _json_dumps(user_query), embed_user_query)

        elif event_type == "assistant_final":
            sql = f"""
            INSERT INTO {table_name} (session_id, turn_id, event_type, payload, time)
            VALUES ($1, $2, $3, $4::jsonb, $5)
            """
            async with pool.acquire() as conn:
                await conn.execute(sql, session_id, turn_uuid, event_type, _json_dumps(payload), time)

        else:
            sql = f"""
            INSERT INTO {table_name} (session_id, turn_id, event_type, payload)
            VALUES ($1, $2, $3, $4::jsonb)
            """
            async with pool.acquire() as conn:
                await conn.execute(sql, session_id, turn_uuid, event_type, _json_dumps(payload))

    async def log_pipeline(session_id: str, turn_id: str, steps: list) -> None:
        """Stores ONE row for the entire pipeline of a turn."""
        payload = {"steps": steps}
        await _insert_event(session_id, turn_id, EVENT_PIPELINE, payload)

    async def log_user_message(
        session_id: str,
        turn_id: Union[str, uuid.UUID],
        user_query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Stores a user message event."""
        payload = {"user_query": user_query, "context": context or {}}
        await _insert_event(session_id, turn_id, EVENT_USER, payload, user_query=user_query)

    async def log_assistant_final(
        session_id: str,
        turn_id: Union[str, uuid.UUID],
        final_answer: Any,
        time: str,
    ) -> None:
        """Stores the final assistant answer event. `final_answer` can be dict/list/string."""
        payload = {"final_answer": final_answer}
        await _insert_event(session_id, turn_id, EVENT_ASSISTANT_FINAL, payload, time=time)

    async def log_tool_call(
        session_id: str,
        turn_id: Union[str, uuid.UUID],
        tool_name: str,
        tool_args: Optional[Dict[str, Any]] = None,
        tool_result: Optional[Any] = None,
        tool_call_id: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        """Stores ONE row per tool call."""
        payload = {
            "tool_name": tool_name,
            "tool_call_id": tool_call_id,
            "tool_args": tool_args or {},
            "tool_result": tool_result,
            "error": error,
        }
        await _insert_event(session_id, turn_id, EVENT_TOOL, payload)

    async def log_sql_query(
        session_id: str,
        turn_id: Union[str, uuid.UUID],
        sql_text: str,
        params: Sequence[Any] = (),
        row_count: Optional[int] = None,
        has_more: Optional[str] = None,
        next_cursor: Optional[str] = "",
        error: Optional[str] = None,
    ) -> None:
        """Stores ONE row per SQL execution."""
        payload = {
            "sql_text": sql_text,
            "params": list(params) if params is not None else [],
            "row_count": row_count,
            "next_cursor": next_cursor,
            "has_more": has_more,
            "error": error,
        }
        await _insert_event(session_id, turn_id, EVENT_SQL, payload)

    async def get_session_history(
        session_id: str,
        limit: int = 200,
        newest_first: bool = False,
    ) -> List[Dict[str, Any]]:
        """Returns raw history rows as JSON-safe dicts."""
        pool = await get_pool()
        order = "DESC" if newest_first else "ASC"

        sql = f"""
        SELECT id, session_id, turn_id, event_type, payload, created_at
        FROM {table_name}
        WHERE session_id = $1
        ORDER BY created_at {order}
        LIMIT $2
        """
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, session_id, limit)

        return [
            {
                "id": r["id"],
                "session_id": r["session_id"],
                "turn_id": str(r["turn_id"]),
                "event_type": r["event_type"],
                "payload": r["payload"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ]

    async def get_turn_history(
        session_id: str,
        turn_id: Union[str, uuid.UUID],
    ) -> List[Dict[str, Any]]:
        """Returns all events for a single turn_id (user -> tool -> sql -> assistant_final)."""
        pool = await get_pool()
        turn_uuid = uuid.UUID(turn_id) if isinstance(turn_id, str) else turn_id

        sql = f"""
        SELECT id, session_id, turn_id, event_type, payload, created_at
        FROM {table_name}
        WHERE session_id = $1 AND turn_id = $2
        ORDER BY created_at ASC
        """
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, session_id, turn_uuid)

        return [
            {
                "id": r["id"],
                "session_id": r["session_id"],
                "turn_id": str(r["turn_id"]),
                "event_type": r["event_type"],
                "payload": r["payload"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ]

    async def delete_session_history(session_id: str) -> None:
        """Deletes all history rows for a session."""
        pool = await get_pool()
        sql = f"DELETE FROM {table_name} WHERE session_id = $1"
        async with pool.acquire() as conn:
            await conn.execute(sql, session_id)

    async def get_memory(query: str) -> list:
        try:
            pool = await get_pool()
            vec = await embed_query_async(query)

            sql = f"""
            WITH _user AS (
            SELECT turn_id
            FROM {table_name}
            WHERE event_type = 'user'
                AND created_at >= NOW() - INTERVAL '3 days'
                AND valid = true
            ORDER BY embed_user_query <=> $1::vector ASC,
                     created_at DESC
            LIMIT 3
            )
            SELECT  h.payload
            FROM _user u
            JOIN {table_name} h
            ON h.turn_id = u.turn_id
            """
            async with pool.acquire() as conn:
                rows = await conn.fetch(sql, vec)
            res = ["Valid examples: "]
            for row in rows:
                res.append(str(row).replace('\\', '').replace('  ', ' '))

            sql = f"""
            WITH _user AS (
            SELECT turn_id
            FROM {table_name}
            WHERE event_type = 'user'
                AND created_at >= NOW() - INTERVAL '3 days'
                AND valid = false
            ORDER BY embed_user_query <=> $1::vector ASC,
                     created_at DESC
            LIMIT 1
            )
            SELECT  h.payload, h.reason
            FROM _user u
            JOIN {table_name} h
            ON h.turn_id = u.turn_id
            """
            async with pool.acquire() as conn:
                rows = await conn.fetch(sql, vec)
            res.append("InValid example: ")
            for row in rows:
                res.append(str(row).replace('\\', '').replace('  ', ' '))

            return res

        except Exception:
            return []

    return HistoryRepo(
        table_name=table_name,
        new_turn_id=new_turn_id,
        ensure_history_schema=ensure_history_schema,
        log_user_message=log_user_message,
        log_assistant_final=log_assistant_final,
        log_tool_call=log_tool_call,
        log_sql_query=log_sql_query,
        log_pipeline=log_pipeline,
        get_session_history=get_session_history,
        get_turn_history=get_turn_history,
        delete_session_history=delete_session_history,
        get_memory=get_memory,
    )
