"""Shared base for data models.

Same role as mini_rag's BaseDataModel: every model gets the database
client and settings from here instead of reaching for globals, which is
what makes them constructible in a test with a different database.
"""
from __future__ import annotations

import re

_VALID_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class BaseDataModel:

    def __init__(self, pg_client, config):
        self.pg_client = pg_client
        self.config = config

    @staticmethod
    def validate_table_name(table_name: str) -> str:
        """A table name reaches SQL as text, never as a parameter."""
        if not _VALID_IDENTIFIER.match(table_name or ""):
            raise ValueError(f"Invalid table name: {table_name!r}")
        return table_name
