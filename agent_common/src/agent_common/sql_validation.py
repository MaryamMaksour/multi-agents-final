# agent_common/sql_validation.py
#
# Replaces the regex/token-scan validation that used to gate db_execute's
# LLM-authored SQL (_ensure_select_only, _ensure_No_embed_in_select,
# _check_tables_allowed). Regex over SQL text is a well-known anti-pattern:
# it can only react to the specific bypass shapes someone thought to test
# (the embed-column guard here used to miss any reference that came after
# a nested subquery's own FROM - see the audit). Parsing the query into a
# real AST and walking it means every table/column reference is found
# regardless of how deeply it's nested, structurally, not by scanning
# tokens in order.
#
# This is still an application-layer check, not a substitute for running
# these queries under a Postgres role with SELECT-only, table-scoped
# grants - see docker/README.md for the recommended GRANT statements. A
# parser bug or an unanticipated construct is still possible; a
# least-privilege DB role is what makes that non-catastrophic.
from __future__ import annotations

from typing import Optional, Sequence

import sqlglot
from sqlglot import exp

# Functions with no legitimate use in a read-only reporting query - most
# either touch the filesystem, sleep/stall the connection, or reach across
# to another server. Not exhaustive (nothing regex/allowlist-based ever
# is), but a real AST walk finds every call site regardless of nesting,
# which is the property that matters here.
_DISALLOWED_FUNCTIONS = {
    "pg_sleep", "pg_sleep_for", "pg_sleep_until",
    "pg_read_file", "pg_read_binary_file",
    "pg_ls_dir", "pg_ls_logdir", "pg_ls_waldir", "pg_ls_tmpdir",
    "pg_stat_file",
    "lo_import", "lo_export",
    "dblink", "dblink_connect", "dblink_exec",
    "pg_terminate_backend", "pg_cancel_backend",
    "pg_reload_conf", "pg_rotate_logfile",
    "set_config", "pg_switch_wal", "pg_create_restore_point",
}

_ALLOWED_ROOTS = (exp.Select, exp.Union)


def validate_readonly_query(sql: str, allowed_tables: Sequence[str]) -> Optional[str]:
    """
    Returns None if `sql` is a safe, read-only, single SELECT/WITH/UNION
    statement that only references `allowed_tables` and never touches an
    embed_*/embedding column. Otherwise returns a human-readable reason,
    meant to be shown back to the LLM so it can correct itself.
    """
    allowed = {t.lower() for t in allowed_tables}
    text = (sql or "").strip()
    if not text:
        return "Empty query."

    try:
        statements = sqlglot.parse(text, read="postgres")
    except Exception as e:
        return f"Could not parse SQL: {e}"

    statements = [s for s in statements if s is not None]
    if len(statements) != 1:
        return "Only a single statement is allowed (no stacked/multiple statements)."

    parsed = statements[0]

    if not isinstance(parsed, _ALLOWED_ROOTS):
        return f"Only SELECT/WITH/UNION queries are allowed, got {type(parsed).__name__}."

    if list(parsed.find_all(exp.Star)):
        return "select * is not allowed - list only the columns needed, or use row_txt instead."

    cte_names = {cte.alias.lower() for cte in parsed.find_all(exp.CTE) if cte.alias}

    referenced_tables = {
        t.name.lower() for t in parsed.find_all(exp.Table) if t.name
    } - cte_names
    disallowed_tables = referenced_tables - allowed
    if disallowed_tables:
        return (
            f"Query references tables outside this agent's domain: {sorted(disallowed_tables)}. "
            f"Allowed tables: {sorted(allowed)}."
        )

    for col in parsed.find_all(exp.Column):
        name = (col.name or "").lower()
        if name == "embedding" or name.startswith("embed_"):
            return "You can not select or reference any embed_*/embedding column - remove it and re-run the tool."

    for func in parsed.find_all((exp.Anonymous, exp.Func)):
        fname = (getattr(func, "name", "") or getattr(func, "sql_name", lambda: "")() or "").lower()
        if fname in _DISALLOWED_FUNCTIONS:
            return f"The function '{fname}' is not allowed in this query."

    return None
