"""What the SQL gate must let through, and what it must not.

Every rejection case here is one an LLM has actually produced or one a
prompt injection would aim for. Every acceptance case is one the domain
prompts explicitly ask the model to write - a validator that rejects
those is worse than no validator, because it fails silently at the one
moment the feature is used.
"""
import pytest

from stores.agents.tools.sql_validation import validate_readonly_query

ALLOWED = ["employees", "teams", "agents_employee"]


@pytest.mark.parametrize("sql", [
    "SELECT id, name FROM employees WHERE status = 'Active'",
    "SELECT COUNT(*) FROM employees WHERE status = $1",
    "SELECT COUNT(id) FROM employees",
    "WITH t AS (SELECT id, name FROM employees) SELECT id, name FROM t",
    "SELECT e.id, e.name FROM employees e JOIN teams t ON t.id = e.id",
    "SELECT id FROM employees UNION SELECT id FROM teams",
    # The semantic-search shapes the prompts tell the model to write.
    "SELECT id, name FROM employees WHERE embed_name <=> $1::vector < 0.35",
    "SELECT id, name FROM employees ORDER BY embed_name <=> $1::vector",
    "SELECT id, name, embed_name <=> $1::vector AS distance FROM employees ORDER BY distance",
])
def test_accepts_legitimate_queries(sql):
    assert validate_readonly_query(sql, ALLOWED) is None


@pytest.mark.parametrize("sql,expected", [
    ("SELECT * FROM employees", "not allowed"),
    ("SELECT id, embed_name FROM employees", "raw embedding"),
    ("SELECT id, embed_name AS v FROM employees", "raw embedding"),
    ("SELECT embedding FROM employees", "raw embedding"),
    # Nesting must not hide anything: a token scan stops at the first
    # FROM it meets, a tree walk does not.
    ("SELECT id FROM (SELECT id, embed_name FROM employees) s", "raw embedding"),
    ("SELECT id FROM customers", "outside this agent"),
    ("SELECT id FROM employees WHERE id IN (SELECT id FROM customers)", "outside this agent"),
    ("SELECT id FROM employees UNION SELECT id FROM customers", "outside this agent"),
    ("SELECT id FROM employees; DROP TABLE employees", "single statement"),
    ("DELETE FROM employees", "SELECT/WITH/UNION"),
    ("UPDATE employees SET name = 'x'", "SELECT/WITH/UNION"),
    ("INSERT INTO employees (id) VALUES (1)", "SELECT/WITH/UNION"),
    ("SELECT id FROM employees WHERE pg_sleep(10) IS NULL", "not allowed"),
    ("SELECT id FROM employees WHERE name = (SELECT pg_read_file('/etc/passwd'))", "not allowed"),
    ("SELECT set_config('app.user_id', 'admin', false)", "not allowed"),
])
def test_rejects_unsafe_queries(sql, expected):
    reason = validate_readonly_query(sql, ALLOWED)
    assert reason is not None, f"should have been rejected: {sql}"
    assert expected.lower() in reason.lower(), reason


def test_query_text_is_never_mutated():
    """Validation must not lowercase the query.

    An earlier version validated and executed the lowercased text, which
    silently turned WHERE status = 'Active' into 'active' and returned
    zero rows for a correct query.
    """
    sql = "SELECT id FROM employees WHERE status = 'Active'"
    before = sql
    validate_readonly_query(sql, ALLOWED)
    assert sql == before
