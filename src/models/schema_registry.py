"""Normalized read access to the domain metadata in schema_data.py.

`schema_data.SCHEMA[table]["columns"]` is inconsistent by table: some
carry a set holding one multi-line DDL string, others a real
`{name: type}` dict. Every consumer used to re-handle that, and the old
column-existence checks papered over it with substring matching against
the stringified blob (so a column named "id" "existed" in every table
that mentioned "id" anywhere). This module parses both shapes once,
into one dict, and everything else asks it.
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Dict, List, Optional

from models.enums import SearchType

from .schema_data import (
    SCHEMA,
    datetime_search_list,
    operation_search_list,
    semantic_search_list,
    word_search_list,
)

# `col_name type NULL,` / `"col name" type NULL,` - one column per line.
_DDL_LINE = re.compile(r'^"?([A-Za-z_][A-Za-z0-9_]*)"?\s+(\S.*?)\s*,?$')

EMBED_PREFIX = "embed_"
EMBEDDING_COLUMN = "embedding"


def _parse_ddl_block(text: str) -> Dict[str, str]:
    columns: Dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip().rstrip(",")
        if not line:
            continue
        match = _DDL_LINE.match(line)
        if match:
            columns[match.group(1).lower()] = match.group(2).strip()
    return columns


@lru_cache(maxsize=None)
def columns_of(table: str) -> Dict[str, str]:
    """Real `{column_name: sql_type}` for one table, both shapes handled."""
    entry = SCHEMA.get(table.lower())
    if not entry:
        return {}

    raw = entry.get("columns")

    if isinstance(raw, dict):
        return {str(k).lower(): str(v) for k, v in raw.items()}

    if isinstance(raw, (set, frozenset)):
        text = next(iter(raw), "")
        return _parse_ddl_block(str(text))

    if isinstance(raw, str):
        return _parse_ddl_block(raw)

    return {}


def known_tables() -> List[str]:
    return sorted(SCHEMA.keys())


def table_exists(table: str) -> bool:
    return table.lower() in SCHEMA


def column_exists(table: str, column: str) -> bool:
    return column.lower() in columns_of(table)


def is_embedding_column(column: str) -> bool:
    name = column.lower()
    return name == EMBEDDING_COLUMN or name.startswith(EMBED_PREFIX)


def visible_columns(table: str) -> Dict[str, str]:
    """Columns an answer may select - embeddings are storage, not data."""
    return {
        name: sql_type
        for name, sql_type in columns_of(table).items()
        if not is_embedding_column(name)
    }


def embedding_column_for(table: str, column: str) -> Optional[str]:
    """The `embed_<column>` companion of a column, when one exists."""
    candidate = f"{EMBED_PREFIX}{column.lower()}"
    return candidate if candidate in columns_of(table) else None


def search_type_of(table: str, column: str) -> SearchType:
    """Which kind of filter this column is meant to be searched with."""
    table_key, column_key = table.lower(), column.lower()

    if column_key in semantic_search_list.get(table_key, []):
        return SearchType.SEMANTIC
    if column_key in word_search_list.get(table_key, []):
        return SearchType.TEXT
    if column_key in operation_search_list.get(table_key, []):
        return SearchType.OPERATOR
    if column_key in datetime_search_list.get(table_key, []):
        return SearchType.DATETIME
    return SearchType.ANY


def paired_columns(table: str, column: str) -> List[str]:
    """Columns that should be searched together with `column`.

    A record's identity is often split across two fields (name +
    shortname, location + address); searching only one of them silently
    misses matches. The old prompts asked the model to remember this;
    this returns it as data.
    """
    pairs = (("name", "shortname"), ("location", "address"))
    column_key = column.lower()
    table_columns = columns_of(table)

    for group in pairs:
        if column_key in group:
            return [c for c in group if c in table_columns and c != column_key]
    return []
