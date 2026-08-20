"""The five tools a SQL domain agent is given."""
import pytest

pytestmark = pytest.mark.asyncio


async def test_lists_only_its_own_tables(hr_tools):
    from stores.agents.specs import get_spec

    result = await hr_tools["get_tables"].ainvoke({})
    assert {entry["table"] for entry in result["tables"]} == set(get_spec("hr").tables)


async def test_schema_returns_real_columns_without_embeddings(hr_tools):
    result = await hr_tools["get_table_schema"].ainvoke({"tables": ["employees"]})
    columns = result["schemas"]["employees"]["columns"]

    assert "name" in columns and "department" in columns
    # Embedding columns are storage. Offering them invites the model to
    # select one, which the SQL gate then rejects - wasting a turn.
    assert not any(name.startswith("embed_") or name == "embedding" for name in columns)


async def test_schema_refuses_another_domains_table(hr_tools):
    result = await hr_tools["get_table_schema"].ainvoke({"tables": ["customers"]})
    assert "error" in result


async def test_column_search_types_are_structured(hr_tools):
    result = await hr_tools["get_column_search_type"].ainvoke(
        {"table": "employees", "columns": ["name", "status", "employmentdate", "not_a_column"]}
    )
    columns = result["columns"]

    assert columns["name"]["search_type"] == "semantic"
    assert columns["name"]["embedding_column"] == "embed_name"
    assert columns["status"]["search_type"] == "text"
    assert columns["employmentdate"]["search_type"] == "datetime"
    # A column that does not exist is reported as such rather than
    # silently treated as searchable - the old substring check called
    # any column real if its name appeared anywhere in the schema blob.
    assert "error" in columns["not_a_column"]


async def test_paging_is_applied_by_code_not_by_the_model(hr_tools, pg_client):
    result = await hr_tools["execute_sql"].ainvoke(
        {"query": "SELECT id, name FROM employees WHERE status = $1", "params": ["Active"], "limit": 2}
    )

    assert result["returned"] == 2
    assert result["total"] == 42
    assert result["has_more"] is True
    assert result["next_offset"] == 2

    executed = pg_client.statements("fetch")[-1]
    assert executed.strip().endswith("LIMIT $2 OFFSET $3")

    # The count comes from the model's own query, so the two can never
    # describe different filters.
    counted = pg_client.statements("fetchval")[-1]
    assert counted.startswith("SELECT COUNT(*) FROM (SELECT id, name FROM employees")


async def test_limit_is_a_ceiling_not_a_suggestion(hr_tools, settings):
    result = await hr_tools["execute_sql"].ainvoke(
        {"query": "SELECT id FROM employees", "params": [], "limit": 9999}
    )
    assert result["limit"] == settings.SQL_MAX_LIMIT


async def test_rejects_model_written_paging(hr_tools):
    result = await hr_tools["execute_sql"].ainvoke(
        {"query": "SELECT id FROM employees LIMIT 5", "params": []}
    )
    assert "error" in result


async def test_rejects_offset_beyond_bound(hr_tools, settings):
    result = await hr_tools["execute_sql"].ainvoke(
        {"query": "SELECT id FROM employees", "params": [], "offset": settings.SQL_MAX_OFFSET + 1}
    )
    assert "error" in result


async def test_rejects_cross_domain_sql(hr_tools):
    result = await hr_tools["execute_sql"].ainvoke(
        {"query": "SELECT id FROM customers", "params": []}
    )
    assert "outside this agent" in result["error"]


async def test_embeds_parameters_server_side(hr_tools, pg_client):
    """A {"embed": ...} parameter becomes a vector here, not in a second LLM turn.

    This is what replaced the embed_query_tool -> Redis token ->
    db_execute round trip, along with the tokens that could expire
    mid-turn or be minted on a replica that did not serve the next call.
    """
    result = await hr_tools["execute_sql"].ainvoke({
        "query": "SELECT id, name, embed_name <=> $1::vector AS distance FROM employees ORDER BY distance",
        "params": [{"embed": "sales director"}],
        "limit": 3,
    })

    assert "rows" in result
    sent = pg_client.arguments("fetch")[-1]
    assert isinstance(sent[0], str) and sent[0].startswith("[0.1")


async def test_distinct_values_validates_the_identifier(hr_tools):
    """Identifiers cannot be parameterized, so they are checked first."""
    assert "values" in await hr_tools["get_distinct_values"].ainvoke(
        {"table": "employees", "column": "department"}
    )
    assert "error" in await hr_tools["get_distinct_values"].ainvoke(
        {"table": "employees", "column": "department; DROP TABLE employees"}
    )
    assert "error" in await hr_tools["get_distinct_values"].ainvoke(
        {"table": "employees", "column": "embed_name"}
    )


async def test_principal_reaches_the_database_layer(hr_tools, pg_client):
    """Identity travels out of band, ready for row-level security.

    It is deliberately not a tool argument: anything the model writes is
    something a prompt injection can rewrite.
    """
    from stores.agents.tools import RequestContext, reset_request_context, set_request_context

    token = set_request_context(RequestContext(session_id="s", turn_id="t", principal="alice"))
    try:
        await hr_tools["execute_sql"].ainvoke({"query": "SELECT id FROM employees", "params": []})
    finally:
        reset_request_context(token)

    assert pg_client.principals[-1] == "alice"


async def test_semantic_search_degrades_when_no_embedding_exists(hr_tools):
    """directors_employees marks director_name semantic but has no embed_ column.

    Reporting semantic search anyway would send the model to write SQL
    against a column that is not there - a failure it cannot recover
    from, because the schema tool never showed it that column either.
    """
    result = await hr_tools["get_column_search_type"].ainvoke(
        {"table": "directors_employees", "columns": ["director_name"]}
    )
    entry = result["columns"]["director_name"]

    assert entry["search_type"] == "text"
    assert "no embedding column" in entry["note"]
    assert "embedding_column" not in entry
