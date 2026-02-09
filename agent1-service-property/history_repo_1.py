
#history_repo_1.py
from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Dict, List, Optional, Sequence, Union

from main.conect_to_DB import get_pool
from main.embeddings import embed_query_async
logger = logging.getLogger(__name__)


# -----------------------------
# History "event types"
# -----------------------------
EVENT_USER = "user"
EVENT_TOOL = "tool"
EVENT_SQL = "sql"
EVENT_ASSISTANT_FINAL = "assistant_final"
EVENT_PIPELINE = "pipeline"


def new_turn_id() -> str:
    """Create a new turn_id (UUID string) to correlate events across one user request."""
    return str(uuid.uuid4())


# -----------------------------
# Schema (single table: history)
# -----------------------------
CREATE_HISTORY_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS history1 (
  id BIGSERIAL PRIMARY KEY,
  session_id TEXT NOT NULL,
  turn_id UUID NOT NULL,
  event_type TEXT NOT NULL,          -- 'user' | 'tool' | 'sql' | 'assistant_final'
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  time  text,
  valid boolean,
  embed_user_query vector(1024),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_history1_session_created
ON history1(session_id, created_at);

CREATE INDEX IF NOT EXISTS idx_history1_session_turn
ON history1(session_id, turn_id);

CREATE INDEX IF NOT EXISTS idx_history1_event_type
ON history1(event_type);
"""


async def ensure_history_schema() -> None:
    """
    Ensures the `history` table exists.
    Call once at startup.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(CREATE_HISTORY_TABLE_SQL)
    logger.info("History1 schema ensured (table: history1).")


# -----------------------------
# Internal helper
# -----------------------------
def _json_dumps(obj: Any) -> str:
    """Safe JSON dumps (handles non-serializable objects by stringifying)."""
    def default(o: Any):
        try:
            return str(o)
        except Exception:
            return "<non-serializable>"

    return json.dumps(obj, ensure_ascii=False, default=default)


async def _insert_event(
    session_id: str,
    turn_id: Union[str, uuid.UUID],
    event_type: str,
    payload: Dict[str, Any],
    user_query: Optional[str]= None,
    time: Optional[str] = None
) -> None:
    pool = await get_pool()

    turn_uuid = uuid.UUID(turn_id) if isinstance(turn_id, str) else turn_id

    if event_type == "user":
        embed_user_query = await embed_query_async(user_query)

        sql = """
        INSERT INTO history1 (session_id, turn_id, event_type, payload,embed_user_query )
        VALUES ($1, $2, $3, $4::jsonb, $5::vector)
        """
         
        async with pool.acquire() as conn:
            await conn.execute(sql, session_id, turn_uuid, event_type, _json_dumps(user_query), embed_user_query)

    elif event_type == "assistant_final":

        sql = """
        INSERT INTO history1 (session_id, turn_id, event_type, payload,time )
        VALUES ($1, $2, $3, $4::jsonb, $5)
        """
     
        async with pool.acquire() as conn:
            await conn.execute(sql, session_id, turn_uuid, event_type, _json_dumps(payload), time)

    else:
        
        sql = """
        INSERT INTO history1 (session_id, turn_id, event_type, payload )
        VALUES ($1, $2, $3, $4::jsonb)
        """
     
        async with pool.acquire() as conn:
            await conn.execute(sql, session_id, turn_uuid, event_type, _json_dumps(payload))



async def log_pipeline(
    session_id: str,
    turn_id: str,
    steps: list[dict],
) -> None:
    """
    Stores ONE row in `history1` for the entire pipeline of a turn.
    steps = [{type, name, args, result}, ..., {type:'final', answer:...}]
    """
    payload = {"steps": steps}
    await _insert_event(session_id, turn_id, EVENT_PIPELINE, payload)

# -----------------------------
# Public API: logging functions
# -----------------------------
async def log_user_message(
    session_id: str,
    turn_id: Union[str, uuid.UUID],
    user_query: str,
    context: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Stores a user message event. One row in `history1`.
    """
    payload = {
        "user_query": user_query,
        "context": context or {},
    }
    
    
    await _insert_event(session_id, turn_id, EVENT_USER, payload,  user_query=user_query)


async def log_assistant_final(
    session_id: str,
    turn_id: Union[str, uuid.UUID],
    final_answer: Any,
    time: str
) -> None:
    """
    Stores the final assistant answer event. One row in `history1`.
    `final_answer` can be dict/list/string.
    """
    payload = {
        "final_answer": final_answer
    }
    await _insert_event(session_id, turn_id, EVENT_ASSISTANT_FINAL, payload, time = time)


async def log_tool_call(
    session_id: str,
    turn_id: Union[str, uuid.UUID],
    tool_name: str,
    tool_args: Optional[Dict[str, Any]] = None,
    tool_result: Optional[Any] = None,
    tool_call_id: Optional[str] = None,
    error: Optional[str] = None,
) -> None:
    """
    Stores ONE row per tool call (your requirement).
    """
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
    """
    Stores ONE row per SQL execution.
    Designed to be called from db_execute tool.
    """
    payload = {
        "sql_text": sql_text,
        "params": list(params) if params is not None else [],
        "row_count": row_count,
        "next_cursor": next_cursor,
        "has_more": has_more,
        "error": error,
    }
    await _insert_event(session_id, turn_id, EVENT_SQL, payload)


# -----------------------------
# Read history back
# -----------------------------
async def get_session_history(
    session_id: str,
    limit: int = 200,
    newest_first: bool = False,
) -> List[Dict[str, Any]]:
    """
    Returns raw history1 rows as JSON-safe dicts.
    """
    pool = await get_pool()
    order = "DESC" if newest_first else "ASC"

    sql = f"""
    SELECT id, session_id, turn_id, event_type, payload, created_at
    FROM history1
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
    """
    Returns all events for a single turn_id (user -> tool -> sql -> assistant_final).
    """
    pool = await get_pool()
    turn_uuid = uuid.UUID(turn_id) if isinstance(turn_id, str) else turn_id

    sql = """
    SELECT id, session_id, turn_id, event_type, payload, created_at
    FROM history1
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
    """
    Deletes all history1 rows for a session.
    """
    pool = await get_pool()
    sql = "DELETE FROM history1 WHERE session_id = $1"
    async with pool.acquire() as conn:
        await conn.execute(sql, session_id)


async def get_memory(query: str) -> list:

    try:
        pool = await get_pool()
        vec  = await embed_query_async(query)

        sql = """
                
                WITH _user AS (
                SELECT turn_id
                FROM history1
                WHERE event_type = 'user'
                    AND created_at >= NOW() - INTERVAL '3 days'
                    AND valid = true
                ORDER BY embed_user_query <=> $1::vector ASC,
                         created_at DESC
                LIMIT 3
                )
                SELECT  h.payload
                FROM _user u
                JOIN history1 h
                ON h.turn_id = u.turn_id

                """
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, vec)
        res = ["Valid examples: "]
        for row in rows:
            res.append(str(row).replace('\\', '').replace('  ',' '))

            sql = """
                
                WITH _user AS (
                SELECT turn_id
                FROM history1
                WHERE event_type = 'user'
                    AND created_at >= NOW() - INTERVAL '3 days'
                    AND valid = false
                ORDER BY embed_user_query <=> $1::vector ASC,
                         created_at DESC
                LIMIT 1
                )
                SELECT  h.payload, h.reason
                FROM _user u
                JOIN history1 h
                ON h.turn_id = u.turn_id

                """
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, vec)
        res.append("InValid example: ")
        for row in rows:
            res.append(str(row).replace('\\', '').replace('  ',' '))

        return res
    
    except:
        return []

'''f = {"context": {"cursor": "null", "turn_id": "null", "session_id": "agents:subsession"}, "user_query": "units in Al Jadaf"}

import asyncio

def save():
    turn_uuid = uuid.UUID("633599c2-66e2-4b53-8eef-0d5fb319e1cd") if isinstance("633599c2-66e2-4b53-8eef-0d5fb319e1cd", str) else "633599c2-66e2-4b53-8eef-0d5fb319e1cd"
    asyncio.run(log_user_message("222222222222222", 
                                 turn_uuid ,
                                     "available units in building LUME" ))
    
    return asyncio.run(get_memory("available units in building LUME"))

print(save())'''