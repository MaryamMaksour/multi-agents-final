"""AST validation for LLM-authored SQL.

Parses the statement with sqlglot and walks the tree, rather than
scanning text: a token scan can only reject the bypass shapes someone
thought to test, while a structural walk finds every table and column
reference regardless of nesting.

Three rules changed from the previous version, each of which was a real
defect:

- The embed-column rule blocked *any* reference to an `embed_*` column,
  including in WHERE and ORDER BY - which is exactly where a pgvector
  search has to reference it. The prompts told the model to write
  `embed_name <=> $1::vector`, and the validator then rejected it, so
  semantic search could never run. The rule that was actually wanted is
  narrower: never *return* a raw vector. A distance computed from one is
  a float and is fine.
- `SELECT *` was rejected by matching any Star node anywhere, which also
  rejected `COUNT(*)` - the one thing every count query needs. Only a
  bare Star in a projection list is rejected now.
- Validation ran against the lowercased query text. That is fine for
  matching, but the lowercased string was also what got executed, which
  silently turned `WHERE status = 'Active'` into `'active'`. Nothing
  here mutates the query; it only inspects it.

This remains an application-layer check. It is not a substitute for
running these queries under a Postgres role that can only see its own
domain's tables - see docker/postgres/least_privilege_roles.sql. A
parser bug is always possible; a least-privilege role is what keeps one
from being catastrophic.
"""
from __future__ import annotations

from typing import Optional, Sequence

import sqlglot
from sqlglot import exp

# Functions with no legitimate use in a read-only reporting query: they
# touch the filesystem, stall the connection, or reach another server.
# Not exhaustive - the AST walk is what makes it reliable, since it finds
# every call site regardless of nesting.
DISALLOWED_FUNCTIONS = {
    "pg_sleep", "pg_sleep_for", "pg_sleep_until",
    "pg_read_file", "pg_read_binary_file",
    "pg_ls_dir", "pg_ls_logdir", "pg_ls_waldir", "pg_ls_tmpdir",
    "pg_stat_file",
    "lo_import", "lo_export",
    "dblink", "dblink_connect", "dblink_exec",
    "pg_terminate_backend", "pg_cancel_backend",
    "pg_reload_conf", "pg_rotate_logfile",
    "set_config", "current_setting",
    "pg_switch_wal", "pg_create_restore_point",
    "query_to_xml", "pg_client_encoding",
}

ALLOWED_ROOTS = (exp.Select, exp.Union)

EMBED_PREFIX = "embed_"
EMBEDDING_COLUMN = "embedding"


def _is_vector_column(name: str) -> bool:
    lowered = (name or "").lower()
    return lowered == EMBEDDING_COLUMN or lowered.startswith(EMBED_PREFIX)


def _projection_error(statement: exp.Expression) -> Optional[str]:
    """Reject bare `*` and raw vector columns in any SELECT's output list.

    Only the projection is inspected, so `WHERE embed_name <=> $1 < 0.35`
    and `ORDER BY embed_name <=> $1` stay legal, and so does
    `embed_name <=> $1 AS distance` - that returns a number, not a vector.
    """
    for select in statement.find_all(exp.Select):
        for projected in select.expressions:
            if isinstance(projected, exp.Star):
                return (
                    "select * is not allowed - list the columns you need, "
                    "or select row_txt for a full-record summary."
                )

            inner = projected.this if isinstance(projected, exp.Alias) else projected
            if isinstance(inner, exp.Column) and _is_vector_column(inner.name):
                return (
                    f"Column '{inner.name}' holds a raw embedding and cannot be returned. "
                    "Use it inside a distance expression instead, e.g. "
                    f"{inner.name} <=> $1::vector AS distance."
                )
    return None


def validate_readonly_query(sql: str, allowed_tables: Sequence[str]) -> Optional[str]:
    """Returns None when `sql` is safe, else a reason to show the model.

    Safe means: one statement, a SELECT/WITH/UNION, referencing only
    `allowed_tables`, returning no raw vector column, and calling no
    disallowed function.
    """
    allowed = {table.lower() for table in allowed_tables}
    text = (sql or "").strip()
    if not text:
        return "Empty query."

    try:
        statements = sqlglot.parse(text, read="postgres")
    except Exception as error:
        return f"Could not parse SQL: {error}"

    statements = [statement for statement in statements if statement is not None]
    if len(statements) != 1:
        return "Only a single statement is allowed (no stacked or multiple statements)."

    parsed = statements[0]

    if not isinstance(parsed, ALLOWED_ROOTS):
        return f"Only SELECT/WITH/UNION queries are allowed, got {type(parsed).__name__}."

    projection_error = _projection_error(parsed)
    if projection_error:
        return projection_error

    # A CTE name is not a real table, so it must not be checked against
    # the allowlist - only the tables the CTEs themselves read from.
    cte_names = {cte.alias.lower() for cte in parsed.find_all(exp.CTE) if cte.alias}
    referenced = {table.name.lower() for table in parsed.find_all(exp.Table) if table.name}
    outside_domain = referenced - cte_names - allowed
    if outside_domain:
        return (
            f"Query references tables outside this agent's domain: {sorted(outside_domain)}. "
            f"Allowed tables: {sorted(allowed)}."
        )

    for function in parsed.find_all(exp.Func):
        # sqlglot models functions it knows as their own node type, and
        # everything else as Anonymous. Only the latter carries the real
        # name in `.name`; for the former, `sql_name()` is the name and
        # `.name` is the first argument. Reading the wrong one is why an
        # earlier version of this check silently matched nothing.
        if isinstance(function, exp.Anonymous):
            name = (function.name or "").lower()
        else:
            name = (function.sql_name() or "").lower()

        if name in DISALLOWED_FUNCTIONS:
            return f"The function '{name}' is not allowed in this query."

    return None
