"""The tool set a SQL domain agent gets, scoped to one domain's tables.

Five tools, down from seven. What changed and why:

- `get_tables` is new. The domain's table list used to be interpolated
  into the system prompt, so the prompt and the allowlist were two
  copies of the same fact that could disagree. Now there is one source.
- `get_column_search_type` replaces `get_filter`, which returned English
  sentences with SQL examples glued into them for the model to re-parse.
  It returns structured data now.
- `execute_sql` replaces `db_execute`. The model no longer writes
  LIMIT/OFFSET, no longer writes a second count query, and no longer
  passes a cursor: pagination and counting are applied by this code.
  That deletes the largest source of malformed-call errors and makes the
  limit a bound the model cannot exceed rather than an instruction it
  might ignore.
- `embed_query_tool` is gone. A parameter written as `{"embed": "text"}`
  is embedded here, server-side, which removes a whole LLM round-trip
  and the Redis vector-token cache it needed (tokens that expired
  mid-turn, and were invisible across replicas before that).
- `execute_next_cursor` is gone with the cursor machinery. Continuation
  is `execute_sql(..., offset=N)`.
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence

from langchain_core.tools import tool

from models import schema_registry as registry
from models.enums import SearchType

from .context import get_request_context
from .sql_validation import validate_readonly_query

logger = logging.getLogger(__name__)

# Marks a parameter whose text should be embedded before the query runs.
EMBED_PARAM_KEY = "embed"


def _vector_literal(vector: Sequence[float]) -> str:
    """pgvector's text input form, for use with a `$n::vector` cast."""
    return "[" + ",".join(str(float(value)) for value in vector) + "]"


def build_sql_toolset(
    allowed_tables: List[str],
    table_notes: Dict[str, str],
    pg_client,
    embed_text: Callable[[str], Awaitable[List[float]]],
    config,
    log_sql: Optional[Callable[..., Awaitable[None]]] = None,
) -> list:
    """Builds the five tools for one domain.

    `allowed_tables` is the only thing that distinguishes one SQL
    domain's tools from another's - which is why merging two domains
    into one agent is passing the union of their table lists, and why
    adding a domain needs no new code here.
    """
    allowed = {table.lower() for table in allowed_tables}
    distance_operator = config.DIST_OP

    async def _log(**fields) -> None:
        if log_sql is None:
            return
        context = get_request_context()
        if not (context.session_id and context.turn_id):
            return
        try:
            await log_sql(session_id=context.session_id, turn_id=context.turn_id, **fields)
        except Exception:
            logger.exception("SQL logging failed")

    def _reject_unknown_table(table: str) -> Optional[Dict[str, Any]]:
        if table not in allowed:
            return {
                "error": f"Table '{table}' is not part of this agent's domain.",
                "allowed_tables": sorted(allowed),
            }
        return None

    async def _resolve_params(params: Sequence[Any]) -> List[Any]:
        """Turn `{"embed": "..."}` placeholders into pgvector literals."""
        resolved: List[Any] = []
        for parameter in params or []:
            if isinstance(parameter, dict) and EMBED_PARAM_KEY in parameter:
                vector = await embed_text(str(parameter[EMBED_PARAM_KEY]))
                resolved.append(_vector_literal(vector))
            else:
                resolved.append(parameter)
        return resolved

    # -----------------------------------------------------------------
    # 1. What can I query?
    # -----------------------------------------------------------------
    @tool
    async def get_tables() -> Dict[str, Any]:
        """List every table this agent may query, with a short note on what each holds.

        Call this first when unsure which table answers the question.
        Any table not listed here is out of scope - another agent owns it.
        """
        return {
            "tables": [
                {"table": table, "about": table_notes.get(table, "")}
                for table in sorted(allowed)
            ]
        }

    # -----------------------------------------------------------------
    # 2. What columns does it have?
    # -----------------------------------------------------------------
    @tool
    async def get_table_schema(tables: List[str]) -> Dict[str, Any]:
        """Return the real columns and SQL types of one or more tables.

        Use the exact column names returned here. Never guess a column.
        Embedding columns are omitted: they are storage for semantic
        search, not data you can return - ask get_column_search_type for
        the embedding column that backs a searchable column.
        """
        schemas: Dict[str, Any] = {}
        for name in tables or []:
            table = (name or "").strip().lower()

            rejection = _reject_unknown_table(table)
            if rejection:
                return rejection

            if not registry.table_exists(table):
                return {"error": f"No schema recorded for table '{table}'."}

            schemas[table] = {"columns": registry.visible_columns(table)}

        if not schemas:
            return {"error": "Pass at least one table name."}
        return {"schemas": schemas}

    # -----------------------------------------------------------------
    # 3. How do I search this column?
    # -----------------------------------------------------------------
    @tool
    async def get_column_search_type(table: str, columns: List[str]) -> Dict[str, Any]:
        """Say how each column should be filtered: semantically, by text, by operator, or as a date.

        Returns one entry per column:
          search_type       - semantic | text | operator | datetime | any
          embedding_column  - the embed_* column to use, for semantic search
          also_search       - sibling columns that should be searched too
                              (name/shortname, location/address), because a
                              record's identity is often split across both
        Follow this exactly. Do not mix a semantic filter and an ILIKE
        filter on the same column.
        """
        table_key = (table or "").strip().lower()

        rejection = _reject_unknown_table(table_key)
        if rejection:
            return rejection

        results: Dict[str, Any] = {}
        for name in columns or []:
            column = (name or "").strip().lower()

            if not registry.column_exists(table_key, column):
                results[column] = {
                    "error": f"Column '{column}' does not exist in '{table_key}'. "
                             "Call get_table_schema for the real column names."
                }
                continue

            search_type = registry.search_type_of(table_key, column)
            embedding_column = registry.embedding_column_for(table_key, column)
            note = ""

            # Some columns are marked for semantic search in the metadata
            # but have no embed_<column> companion recorded (several of
            # the joined views are like this). Reporting semantic search
            # for one of them sends the model off to write SQL against a
            # column that does not exist, and the turn fails on a
            # Postgres error it cannot act on. Fall back to text search
            # and say so instead.
            if search_type is SearchType.SEMANTIC and not embedding_column:
                search_type = SearchType.TEXT
                note = (
                    f"'{column}' has no embedding column, so semantic search is "
                    "not available for it - matching on text instead."
                )

            entry: Dict[str, Any] = {
                "search_type": search_type.value,
                "also_search": registry.paired_columns(table_key, column),
            }
            if note:
                entry["note"] = note

            if search_type is SearchType.SEMANTIC:
                entry["embedding_column"] = embedding_column
                entry["distance_operator"] = distance_operator
                entry["max_distance"] = 0.35
            elif search_type is SearchType.TEXT:
                entry["match"] = "COALESCE(col, '') ILIKE '%' || $n || '%'"
            elif search_type is SearchType.DATETIME:
                entry["cast"] = "col::timestamp"

            results[column] = entry

        if not results:
            return {"error": "Pass at least one column name."}
        return {"table": table_key, "columns": results}

    # -----------------------------------------------------------------
    # 4. Run the query.
    # -----------------------------------------------------------------
    @tool
    async def execute_sql(
        query: str,
        params: Optional[List[Any]] = None,
        offset: int = 0,
        limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Run one read-only SELECT and return its rows, with paging handled for you.

        query   a single SELECT or WITH statement. Parameterize every
                value as $1, $2, ... Do NOT write LIMIT or OFFSET - they
                are added here.
        params  values for $1, $2, ... in order. For a semantic search,
                pass {"embed": "some text"} and it is turned into a
                vector here; reference it as $n::vector.
        offset  row to start from; use it to page through results.
        limit   rows to return; capped by the server.

        Returns {rows, returned, total, limit, offset, has_more,
        next_offset}. `total` is the count of all matching rows, so
        has_more is exact.
        """
        effective_limit = config.SQL_DEFAULT_LIMIT if limit is None else int(limit)
        effective_limit = max(1, min(effective_limit, config.SQL_MAX_LIMIT))

        try:
            effective_offset = max(0, int(offset or 0))
        except (TypeError, ValueError):
            return {"error": "offset must be an integer."}

        if effective_offset > config.SQL_MAX_OFFSET:
            return {
                "error": f"offset must be at most {config.SQL_MAX_OFFSET}. "
                         "Narrow the query with more filters instead of paging further."
            }

        validation_error = validate_readonly_query(query, allowed)
        if validation_error:
            await _log(sql_text=query, params=params or [], error=validation_error)
            return {"error": validation_error}

        lowered = (query or "").lower()
        if " limit " in f" {lowered} " or " offset " in f" {lowered} ":
            return {
                "error": "Do not write LIMIT or OFFSET in the query - pass the "
                         "`limit` and `offset` arguments instead."
            }

        try:
            resolved = await _resolve_params(params or [])
        except Exception as error:
            logger.exception("Embedding a query parameter failed")
            return {"error": f"Could not embed a parameter: {error}"}

        # The model writes the filter once; the count is derived from it,
        # so the two can never disagree the way a hand-written count
        # query could.
        count_sql = f"SELECT COUNT(*) FROM ({query}) AS _matched"
        paged_sql = f"{query} LIMIT ${len(resolved) + 1} OFFSET ${len(resolved) + 2}"

        context = get_request_context()

        try:
            async with pg_client.acquire(principal=context.principal) as conn:
                total = await conn.fetchval(count_sql, *resolved)
                records = await conn.fetch(paged_sql, *resolved, effective_limit, effective_offset)

        except Exception as error:
            message = str(error)
            logger.exception("execute_sql failed")
            await _log(sql_text=query, params=params or [], error=message)
            return {"error": f"SQL error: {message}"}

        rows = [dict(record) for record in records]
        total = int(total or 0)
        next_offset = effective_offset + len(rows)

        await _log(
            sql_text=query,
            params=params or [],
            row_count=len(rows),
            total=total,
        )

        return {
            "rows": rows,
            "returned": len(rows),
            "total": total,
            "limit": effective_limit,
            "offset": effective_offset,
            "has_more": next_offset < total,
            "next_offset": next_offset if next_offset < total else None,
        }

    # -----------------------------------------------------------------
    # 5. What values does this column actually hold?
    # -----------------------------------------------------------------
    @tool
    async def get_distinct_values(table: str, column: str) -> Dict[str, Any]:
        """List the distinct values stored in a column.

        Use this before filtering on a status/stage/type column, so the
        filter matches values that really exist instead of guessed ones.
        """
        table_key = (table or "").strip().lower()
        column_key = (column or "").strip().lower()

        rejection = _reject_unknown_table(table_key)
        if rejection:
            return rejection

        # Identifiers cannot be parameterized, so they are checked
        # against the parsed schema before being put into the SQL text.
        if not registry.column_exists(table_key, column_key):
            return {
                "error": f"Column '{column}' does not exist in '{table_key}'. "
                         "Call get_table_schema for the real column names."
            }

        if registry.is_embedding_column(column_key):
            return {"error": f"Column '{column_key}' holds embeddings and has no readable values."}

        context = get_request_context()
        sql = f"SELECT DISTINCT {column_key} AS value FROM {table_key} LIMIT 100"

        try:
            async with pg_client.acquire(principal=context.principal) as conn:
                records = await conn.fetch(sql)
        except Exception as error:
            logger.exception("get_distinct_values failed")
            return {"error": f"SQL error: {error}"}

        values = [record["value"] for record in records]
        if not values:
            return {"table": table_key, "column": column_key, "values": [], "note": "all values are NULL"}

        truncated = len(values) >= 100
        return {
            "table": table_key,
            "column": column_key,
            "values": values[:50],
            "truncated": truncated,
            "note": "more than 100 distinct values; only a sample is shown" if truncated else "",
        }

    return [get_tables, get_table_schema, get_column_search_type, execute_sql, get_distinct_values]
