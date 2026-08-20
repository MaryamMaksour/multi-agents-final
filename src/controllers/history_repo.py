# controllers/history_repo.py
#
# Every sub-agent service used a byte-for-byte identical implementation of
# this file before, differing only in one hardcoded table name
# (history1..history6). build_history_repo() is that same implementation,
# parameterized by table_name instead of copy-pasted per service.
#
# Redesigned so semantic memory recall actually works: the schema now has a
# real `reason` column, `valid` is computed automatically from each turn's
# outcome (no manual curation needed), and it's set on the 'user' row via an
# UPDATE issued from log_assistant_final once the outcome is known - the
# validity of a turn can only be known after it completes, not when the user
# message is first logged. get_memory() returns the full trace for each
# matched turn (the user question plus its assistant_final row, whose
# payload already carries every tool call - name, args, result - from
# extract_pipeline()), not just the final answer text, so prompts get real
# reasoning/tool-calling examples, not just Q/A pairs.
from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence, Union

from stores.db import get_pool
from stores.llm import embed_query_async

logger = logging.getLogger(__name__)

EVENT_USER = "user"
EVENT_TOOL = "tool"
EVENT_SQL = "sql"
EVENT_ASSISTANT_FINAL = "assistant_final"
EVENT_PIPELINE = "pipeline"

_VALID_TABLE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_MAX_REASON_LEN = 500


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


def _find_error(payload: Any) -> Optional[str]:
    """
    Walks a final-answer payload (a dict, or a list of pipeline steps) looking
    for an {"error": ...} anywhere shallow in it. Used to auto-compute
    turn validity: a turn with no error anywhere in its outcome is a good
    few-shot example; a turn that errored is kept too (as a short-lived
    "what not to do" example) with the error text as its reason.
    """
    def _from_dict(d: dict) -> Optional[str]:
        if "error" in d and d["error"]:
            return str(d["error"])[:_MAX_REASON_LEN]
        for v in d.values():
            found = _find_error(v)
            if found:
                return found
        return None

    if isinstance(payload, dict):
        return _from_dict(payload)
    if isinstance(payload, list):
        for item in payload:
            found = _find_error(item)
            if found:
                return found
    return None


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
      reason text,
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

    async def _mark_turn_validity(turn_id: Union[str, uuid.UUID], valid: bool, reason: Optional[str]) -> None:
        """
        Stamps the outcome onto this turn's 'user' row, which is what
        get_memory() filters and orders by (it's the row carrying the
        semantic embedding of the question). Validity can only be known
        after the turn finishes, so this runs from log_assistant_final,
        not from log_user_message.
        """
        pool = await get_pool()
        turn_uuid = uuid.UUID(turn_id) if isinstance(turn_id, str) else turn_id
        sql = f"""
        UPDATE {table_name}
        SET valid = $1, reason = $2
        WHERE turn_id = $3 AND event_type = 'user'
        """
        async with pool.acquire() as conn:
            await conn.execute(sql, valid, reason, turn_uuid)

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
        """
        Stores the final assistant answer event - `final_answer` is
        typically the full step-by-step pipeline (tool calls with their
        args/results, then the final answer) produced by
        utils.pipeline_utils.extract_pipeline(), which is what makes this
        row usable as a "thinking + tool calling" few-shot example, not
        just a bare answer. Also auto-marks this turn's 'user' row valid/
        invalid based on whether an error shows up anywhere in the outcome.
        """
        payload = {"final_answer": final_answer}
        await _insert_event(session_id, turn_id, EVENT_ASSISTANT_FINAL, payload, time=time)

        error_reason = _find_error(final_answer)
        try:
            await _mark_turn_validity(turn_id, valid=(error_reason is None), reason=error_reason)
        except Exception:
            logger.exception("Failed to mark turn validity for turn_id=%s", turn_id)

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

    async def _fetch_good_examples(conn, vec, limit: int) -> list:
        sql = f"""
        WITH _match AS (
            SELECT turn_id
            FROM {table_name}
            WHERE event_type = 'user'
              AND valid = true
              AND created_at >= NOW() - INTERVAL '3 days'
            ORDER BY embed_user_query <=> $1::vector ASC, created_at DESC
            LIMIT $2
        )
        SELECT u.payload AS question, f.payload AS trace
        FROM _match m
        JOIN {table_name} u ON u.turn_id = m.turn_id AND u.event_type = 'user'
        JOIN {table_name} f ON f.turn_id = m.turn_id AND f.event_type = 'assistant_final'
        """
        rows = await conn.fetch(sql, vec, limit)
        return [
            {"question": r["question"], "trace": r["trace"]}
            for r in rows
        ]

    async def _fetch_bad_examples(conn, vec, limit: int) -> list:
        sql = f"""
        WITH _match AS (
            SELECT turn_id, reason
            FROM {table_name}
            WHERE event_type = 'user'
              AND valid = false
              AND created_at >= NOW() - INTERVAL '3 days'
            ORDER BY embed_user_query <=> $1::vector ASC, created_at DESC
            LIMIT $2
        )
        SELECT u.payload AS question, m.reason AS reason
        FROM _match m
        JOIN {table_name} u ON u.turn_id = m.turn_id AND u.event_type = 'user'
        """
        rows = await conn.fetch(sql, vec, limit)
        return [
            {"question": r["question"], "reason": r["reason"]}
            for r in rows
        ]

    async def get_memory(query: str) -> list:
        """
        Returns up to 3 semantically similar past turns that succeeded
        (each with its full question + tool-calling/thinking trace, so the
        model gets real worked examples, not just answers), plus up to 1
        similar past turn that failed (with its reason, as a "don't do
        this" example). Each lookup fails independently - a broken query
        never erases the other one's results.
        """
        examples: list = []
        try:
            pool = await get_pool()
            vec = await embed_query_async(query)

            try:
                async with pool.acquire() as conn:
                    good = await _fetch_good_examples(conn, vec, limit=3)
                if good:
                    examples.append({"valid_examples": good})
            except Exception:
                logger.exception("get_memory: valid-example lookup failed")

            try:
                async with pool.acquire() as conn:
                    bad = await _fetch_bad_examples(conn, vec, limit=1)
                if bad:
                    examples.append({"invalid_examples": bad})
            except Exception:
                logger.exception("get_memory: invalid-example lookup failed")

        except Exception:
            logger.exception("get_memory failed")

        return examples

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
