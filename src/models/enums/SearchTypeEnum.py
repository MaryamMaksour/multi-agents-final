from enum import Enum


class SearchType(str, Enum):
    """How a column should be filtered.

    Returned as structured data by the get_column_search_type tool - the
    old get_filter returned English prose with SQL glued into it, which
    the model had to re-parse.
    """
    SEMANTIC = "semantic"     # embed_<col> <=> $n::vector
    TEXT = "text"             # ILIKE
    OPERATOR = "operator"     # =, >, <, BETWEEN
    DATETIME = "datetime"     # ::timestamp casts
    ANY = "any"
