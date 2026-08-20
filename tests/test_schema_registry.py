"""Normalizing two different shapes of column metadata into one."""
from models import schema_registry as registry
from models.enums import SearchType


def test_parses_the_ddl_string_shape():
    """employees stores one multi-line DDL string."""
    columns = registry.columns_of("employees")
    assert columns["name"]
    assert "department" in columns
    assert "embed_name" in columns


def test_parses_the_dict_shape():
    """directors_employees stores a real name->type dict."""
    columns = registry.columns_of("directors_employees")
    assert "director_name" in columns


def test_column_existence_is_exact_not_substring():
    """The old check asked whether the name appeared anywhere in the blob.

    That made "id" a valid column of every table that mentioned it, and
    "name" a valid column of any table with an "embed_name".
    """
    assert registry.column_exists("employees", "name")
    assert not registry.column_exists("employees", "salary")
    assert not registry.column_exists("employees", "am")


def test_embedding_columns_are_identified_and_hidden():
    assert registry.is_embedding_column("embed_name")
    assert registry.is_embedding_column("embedding")
    assert not registry.is_embedding_column("name")
    assert "embed_name" not in registry.visible_columns("employees")


def test_search_types_come_from_the_curated_lists():
    assert registry.search_type_of("employees", "name") is SearchType.SEMANTIC
    assert registry.search_type_of("employees", "status") is SearchType.TEXT
    assert registry.search_type_of("employees", "employmentdate") is SearchType.DATETIME
    assert registry.search_type_of("employees", "id") is SearchType.OPERATOR


def test_columns_marked_semantic_without_an_embedding_are_known():
    """Documents a real gap in the metadata.

    Two of the joined views - directors_employees and customers_deals -
    list columns under semantic search that have no embed_<column>
    companion in the recorded schema. Searching one semantically would
    reference a column that does not exist, so the tool downgrades those
    to text search (see the companion test in test_tools.py).

    The recorded schema may simply be out of date with the database. If
    those columns do have embeddings, add them to schema_data.py and
    this list shrinks; the check is here so the gap stays visible either
    way rather than surfacing as a failed query.
    """
    from models.schema_data import semantic_search_list
    from stores.agents.specs import get_spec

    gaps = {
        (table, column)
        for domain in ("hr", "crm")
        for table in get_spec(domain).tables
        for column in semantic_search_list.get(table, [])
        if not registry.embedding_column_for(table, column)
    }

    known_gaps = {
        (table, column)
        for table in ("directors_employees", "customers_deals")
        for column in semantic_search_list.get(table, [])
        if not registry.embedding_column_for(table, column)
    }

    assert gaps == known_gaps, f"new tables have the same gap: {sorted(gaps - known_gaps)}"
