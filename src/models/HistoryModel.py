"""Per-domain conversation history and audit log.

One table per domain, holding every event of every turn: the user's
question, each tool call, each SQL statement, and the final answer.

Built with the `create_instance` pattern rather than a plain
constructor, for the reason the pattern exists: creating the table and
its indexes is async, and `__init__` cannot await. `create_instance` is
an async classmethod that constructs the model and ensures its schema
in one step, so no caller can end up with a model whose table does not
exist yet.

Two payload keys on the final-answer row matter, and the difference
between them is deliberate:

  trace  the full pipeline including every tool result. This is the
         audit record - what was asked, what ran, what came back.
  shape  the same pipeline with results removed. This is what the
         semantic memory reads back as few-shot examples.

Examples exist to show the model how to reason and which tools to call.
That is entirely carried by the shape. Feeding back the rows as well
would put one user's query results into another user's prompt, which is
a data leak with no upside - the reasoning is what teaches, not the
data it happened to return.
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Dict, List, Optional, Sequence, Union

from models.enums import EventType

from .BaseDataModel import BaseDataModel

logger = logging.getLogger(__name__)

MAX_REASON_LENGTH = 500


def new_turn_id() -> str:
    """Correlates every event belonging to one user request."""
    return str(uuid.uuid4())


def _json_dumps(value: Any) -> str:
    def fallback(obj: Any) -> str:
        try:
            return str(obj)
        except Exception:
            return "<non-serializable>"

    return json.dumps(value, ensure_ascii=False, default=fallback)


def find_error(payload: Any) -> Optional[str]:
    """First error found anywhere in a turn's outcome, if any.

    Drives the `valid` flag: a turn that finished without an error is a
    good example to learn from, and one that errored is kept as a short-
    lived counter-example with its reason.
    """
    if isinstance(payload, dict):
        if payload.get("error"):
            return str(payload["error"])[:MAX_REASON_LENGTH]
        for value in payload.values():
            found = find_error(value)
            if found:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = find_error(item)
            if found:
                return found
    return None


class HistoryModel(BaseDataModel):

    def __init__(self, pg_client, config, table_name: str):
        super().__init__(pg_client, config)
        self.table_name = self.validate_table_name(table_name)

    @classmethod
    async def create_instance(cls, pg_client, config, table_name: str) -> "HistoryModel":
        instance = cls(pg_client, config, table_name)
        await instance.init_table()
        return instance

    async def init_table(self) -> None:
        table = self.table_name
        dimensions = int(self.config.EMBEDDING_MODEL_SIZE)

        create_sql = f"""
        CREATE TABLE IF NOT EXISTS {table} (
          id BIGSERIAL PRIMARY KEY,
          session_id TEXT NOT NULL,
          turn_id UUID NOT NULL,
          event_type TEXT NOT NULL,
          payload JSONB NOT NULL DEFAULT '{{}}'::jsonb,
          duration_seconds NUMERIC,
          valid BOOLEAN,
          reason TEXT,
          embed_user_query vector({dimensions}),
          created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX IF NOT EXISTS idx_{table}_session_created
          ON {table}(session_id, created_at);

        CREATE INDEX IF NOT EXISTS idx_{table}_turn
          ON {table}(turn_id, event_type);

        CREATE INDEX IF NOT EXISTS idx_{table}_examples
          ON {table}(event_type, valid, created_at);
        """

        async with self.pg_client.acquire() as conn:
            try:
                async with conn.transaction():
                    await conn.execute(create_sql)
            except Exception:
                # Under least privilege the agent role has no CREATE on
                # the schema - the history tables are created up front by
                # docker/postgres/least_privilege_roles.v2.sql instead, so
                # that an agent can write its own history and nothing
                # else. Missing CREATE is therefore expected; a missing
                # table is not.
                exists = await conn.fetchval("SELECT to_regclass($1)", table)
                if not exists:
                    raise
                logger.info(
                    "History table %s already exists and cannot be created by this "
                    "role - continuing.", table,
                )
                return

        logger.info("History schema ready (table: %s).", table)

    # -- writes -------------------------------------------------------
    async def _insert(
        self,
        session_id: str,
        turn_id: Union[str, uuid.UUID],
        event_type: str,
        payload: Any,
        embedding: Optional[str] = None,
        duration_seconds: Optional[float] = None,
    ) -> None:
        turn_uuid = uuid.UUID(turn_id) if isinstance(turn_id, str) else turn_id
        sql = f"""
        INSERT INTO {self.table_name}
            (session_id, turn_id, event_type, payload, embed_user_query, duration_seconds)
        VALUES ($1, $2, $3, $4::jsonb, $5::vector, $6)
        """
        async with self.pg_client.acquire() as conn:
            await conn.execute(
                sql, session_id, turn_uuid, event_type,
                _json_dumps(payload), embedding, duration_seconds,
            )

    async def log_user_message(
        self,
        session_id: str,
        turn_id: str,
        user_query: str,
        embedding: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        await self._insert(
            session_id, turn_id, EventType.USER.value,
            {"user_query": user_query, "context": context or {}},
            embedding=embedding,
        )

    async def log_tool_call(
        self,
        session_id: str,
        turn_id: str,
        tool_name: str,
        tool_args: Optional[Dict[str, Any]] = None,
        tool_result: Any = None,
        tool_call_id: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        await self._insert(
            session_id, turn_id, EventType.TOOL.value,
            {
                "tool_name": tool_name,
                "tool_call_id": tool_call_id,
                "tool_args": tool_args or {},
                "tool_result": tool_result,
                "error": error,
            },
        )

    async def log_sql(
        self,
        session_id: str,
        turn_id: str,
        sql_text: str,
        params: Sequence[Any] = (),
        row_count: Optional[int] = None,
        total: Optional[int] = None,
        error: Optional[str] = None,
    ) -> None:
        await self._insert(
            session_id, turn_id, EventType.SQL.value,
            {
                "sql_text": sql_text,
                "params": list(params) if params is not None else [],
                "row_count": row_count,
                "total": total,
                "error": error,
            },
        )

    async def log_assistant_final(
        self,
        session_id: str,
        turn_id: str,
        final_answer: Any,
        trace: List[Dict[str, Any]],
        shape: List[Dict[str, Any]],
        duration_seconds: Optional[float] = None,
    ) -> None:
        """Records the outcome and stamps this turn's validity.

        Validity can only be known once the turn has finished, so it is
        written here with an UPDATE onto the turn's user row - the row
        that carries the question's embedding, and therefore the row the
        memory lookup filters and orders by.
        """
        await self._insert(
            session_id, turn_id, EventType.ASSISTANT_FINAL.value,
            {"final_answer": final_answer, "trace": trace, "shape": shape},
            duration_seconds=duration_seconds,
        )

        reason = find_error(final_answer) or find_error(trace)
        try:
            await self.mark_turn_validity(turn_id, valid=reason is None, reason=reason)
        except Exception:
            logger.exception("Could not mark turn validity for turn_id=%s", turn_id)

    async def mark_turn_validity(self, turn_id: str, valid: bool, reason: Optional[str]) -> None:
        turn_uuid = uuid.UUID(turn_id) if isinstance(turn_id, str) else turn_id
        sql = f"""
        UPDATE {self.table_name}
           SET valid = $1, reason = $2
         WHERE turn_id = $3 AND event_type = $4
        """
        async with self.pg_client.acquire() as conn:
            await conn.execute(sql, valid, reason, turn_uuid, EventType.USER.value)

    # -- reads --------------------------------------------------------
    async def get_session_history(self, session_id: str, limit: int = 200) -> List[Dict[str, Any]]:
        sql = f"""
        SELECT id, session_id, turn_id, event_type, payload, created_at
          FROM {self.table_name}
         WHERE session_id = $1
         ORDER BY created_at ASC
         LIMIT $2
        """
        async with self.pg_client.acquire() as conn:
            records = await conn.fetch(sql, session_id, limit)

        return [
            {
                "id": record["id"],
                "session_id": record["session_id"],
                "turn_id": str(record["turn_id"]),
                "event_type": record["event_type"],
                "payload": record["payload"],
                "created_at": record["created_at"].isoformat() if record["created_at"] else None,
            }
            for record in records
        ]

    async def delete_session_history(self, session_id: str) -> None:
        sql = f"DELETE FROM {self.table_name} WHERE session_id = $1"
        async with self.pg_client.acquire() as conn:
            await conn.execute(sql, session_id)
