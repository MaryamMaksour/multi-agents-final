
# tools.py 
from __future__ import annotations

import json
import logging
import re
import base64

from typing import Any, Dict, Optional, Sequence, List

from langchain_core.tools import tool

from main.static import SCHEMA as schema
from main.static import  semantic_search_list, word_search_list, operation_search_list, domain
from main.embeddings import embed_query_async
from main.conect_to_DB import get_pool
from main.config import DIST_OP
from main.vector_store import store_vector, get_vector

from .history_repo_1 import log_sql_query
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class QueryResult():

    rows: list[Any]
    row_count: int
    has_more: bool
    next_cursor: str


# ============================================================
# Cursor Encoding / Decoding (OPAQUE, QUERY‑LOCKED)
# ============================================================
def encode_cursor(payload: Dict[str, Any]) -> str:
    return base64.b64encode(json.dumps(payload).encode()).decode()


def decode_cursor(cursor: str) -> Dict[str, Any]:
    return json.loads(base64.b64decode(cursor.encode()).decode())


# --- Minimal query hardening ---
_DISALLOWED = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke)\b",
    flags=re.IGNORECASE,
)

def _ensure_select_only(sql: str) -> None:
    s = str(sql)
    s = (s or "").strip()
    if not s:
        return ValueError("Empty query.")
    low = s.lower()

    result = ""

    if ";" in low:
        # prevent stacked statements
        result += "Semicolons are not allowed. re-run the tool without ; ."
    if _DISALLOWED.search(low) or not (low.startswith("select") or low.startswith("with")):#
        result += "Only SELECT/WITH queries are allowed. rerun the tool using only select/with."
    if "*" in low and (not "count" in low):
        result += "select * Not allowed list only columns needed or use column row_txt insted and re-run the tool."

    for w in s.split():
        if w == "FROM":
            break
        if w[:6] == "embed_" or w[2:8] == "embed_" or w == "embedding":
            result += "You can not return any embed column in select, delete it and re-run the tool again"
            break

        
    if result != "":
        return ValueError(result)
      
    return sql

def _ensure_No_embed_in_select(sql: str) :

    s = str(sql).lower()
    s = (s or "").strip()

    for i in range (len(s.split())):
        if s[i] == "select":
            while s[i] != 'from':
                i += 1

                if s[i].find("embed"):
                    return ValueError("can not select embed column")
                
    return sql


def _validate_identifier(name: str) -> str:
    """
    Validate SQL identifiers (table/column) to avoid injection.
    Only letters, numbers, and underscore, must start with letter/underscore.
    """
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name or ""):
        return ValueError(f"Invalid identifier: {name!r}")
    return name



async def _semantic_table_records(
    query_text: str,
    table: str,
    max_results: int,
    embedding_col: str = "embedding",
    text_col: str = "row_txt",
) -> Dict[str, Any]:
    
    """
    Semantic search with pgvector distance operator (<=>).
    Uses whitelisting for identifiers and parameter for vector.
    """
    table = _validate_identifier(table)

    # Whitelist known tables from schema
    if table.lower() not in domain[3]:
        return {"error": f"Unknown table: {table}. use one of the tables in the schema only {domain[3]}"}

    # embed_query expected to return a vector-like structure (list[float] etc.)
    try:
        query_vec = await embed_query_async(query_text)
    except Exception as e:
        return {"error": f" error with embedding: {e}"}
    

    max_results = max(2, min(max_results, 10))

    sql = f"""
        SELECT {text_col}
        FROM {table}
        ORDER BY {embedding_col} {DIST_OP} $1::vector
        LIMIT $2
    """

    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(sql, query_vec, max_results)
            items = [r[text_col] for r in rows]

            return {"rows": items,
                    "row_count": max_results,
                    "has_more": False,
                    "next_cursor": "" }
        
        except Exception as e:
            logger.exception("Semantic search failed")
            return {"error": f"SQL error: {str(e)}"}


@tool
async def get_table_records(query: str, table_name: str, mx: int = 5) -> Dict[str, Any]:
    """
    Semantic name resolution tool.
    Use ONLY for vague, semantic, name-based lookups, or other tools did not give answer (secondry tool).
    Returns JSON ONLY.
    """
    table_name = table_name.lower()
    if not isinstance(query, str) or not query.strip():
        return {"error": "Invalid query."}

    table = (table_name or "").lower().strip()
    if table not in domain[3]:
        return {"error": f"Unknown table: {table_name}. use one of the tables in the schema only {domain[3]}"}

    mx = max(3, min(int(mx), 6))
    return await _semantic_table_records(
        query_text=query,
        table=table,
        max_results=mx,
    )


@tool
async def db_execute(   query: str,
                        params: Sequence[Any],
                        offset: int,
                        count_query: str,
                        count_params: Sequence[Any],
                        cursor: str ,
                        session_id: Optional[str] = None,  
                        turn_id: Optional[str] = None,
                     
                       ) -> Dict[str, Any]:
    """
    search in data based on select SQL query with cursor-based pagination.
    Execute a SELECT/WITH query safely-ish (no stacked statements).
    will take input as (query (as string) as sql statment string to return the answer record with limit $n offset $m, 
                        params as sequence of all values for this query inclouded limit and offset; len(param) >= 2,
                        offset (int) value needed for do the pagenation,
                        count_query (as string) to get the count off all row matching the filters NO LIMIT OT OFFSET select count(id) from table_name where {filters}
                        count_params  as sequence of all values for this count query
                        cursor for pagination  if No then "" should be string not None
                        ) -> return dict{{"rows": all data from query, 
                        "row_count": result from count_query, 
                        "has_more": has_more if total > limit+ offset,
                        "next_cursor": next_cursor} } 

    """
    
    
    error_msg = None
    row_count = None

    try:
        if cursor:
            state = decode_cursor(cursor)
            offset = state["offset"]
            query = state["query"]
        else:
            offset = 0
            
        query = _ensure_select_only(query)
        if type(query) is not str :
            return f"error { query }"
        
        
        query = _ensure_No_embed_in_select(query)
        if type(query) is not str :
            return f"error {query }"
        

        count_query = _ensure_select_only(count_query)
        if type(count_query) is not str :
            return f"error { count_query }"
        

        count_query = _ensure_No_embed_in_select(count_query)
        if type(count_query) is not str :
            return f"error {count_query }"
        
        query = query.lower()
        if "limit $" not in query:
            return f"error limit $n should be in the query in this shape"
        
        if "offset $" not in query:
            return f"error offset $n should be in the query in this shape"
        
        
        resolved_params = []
        for p in params:
            if isinstance(p, str) and p.startswith("vec_"):
                p = get_vector(p)  
            resolved_params.append(p)

        resolved_count_params = []
        for p in count_params:
            if isinstance(p, str) and p.startswith("vec_"):
                p = get_vector(p)   
            resolved_count_params.append(p)

        pool = await get_pool()
        async with pool.acquire() as conn:
              try:
                rows = await conn.fetch(query, *resolved_params)
                # Convert asyncpg Records to JSON-safe dicts
                data = [dict(r) for r in rows]
                row_count = len(data)

                total = await conn.fetch(count_query, *resolved_count_params)
                total = total[0][0]

                next_offset = offset + row_count
                has_more = next_offset < total
                next_cursor = ""
                if has_more:
                    next_cursor = encode_cursor({
                        "offset": next_offset,
                        "query": query
                    })


                if session_id and turn_id:
                    await log_sql_query(
                        session_id=session_id,
                        turn_id=turn_id,
                        sql_text=query,
                        params=params,
                        row_count=row_count,
                        has_more = has_more,
                        next_cursor= next_cursor,
                        error=None,
                    )
            
                return {"rows": data, 
                        "row_count": total, 
                        "has_more": has_more,
                        "next_cursor": next_cursor}
              
              except Exception as e:
                  return f"error {e}"
                    

    except Exception as e:

        error_msg = str(e)

        if session_id and turn_id:
            try:
                await log_sql_query(
                    session_id=session_id,
                    turn_id=turn_id,
                    sql_text=query,
                    params=params,
                    row_count=row_count,
                    error=error_msg,
                )

            except Exception:
                # avoid double-failing the tool because logging failed
                pass

        logger.exception(f"db_execute failed + {error_msg}")
        return {"error": error_msg}

                

@tool
async def embed_query_tool(query: str):
    "convert any value to vector use it when need to do semantic search in db_execute (every column value saperated)"
    embed = await embed_query_async(query)

    token = store_vector(embed)
    return {"vector_token": token}

@tool
async def get_filter(columns: List[str], table_name) -> List[str]:
    """
    input list of column want to use it query, and table name of this columns
    use to know what type of filter search should used for this columns
    
    return the list of the filters type
    """
    try:
        table_name = table_name.lower()
        if table_name not in domain[3]:
                return f"{table_name} Not part of this agent, use other tables from {domain[3]}"
        filters = []
        for column in columns:
            res = ""
            if column in semantic_search_list[table_name]:
                res = f" vector filters search for column {column} in table {table_name}. "
            elif column in word_search_list[table_name]:
                res = f" ILIKE filters search for column {column} in table {table_name}. "
            elif column in operation_search_list[table_name]:
                res = f" Operators search for column {column} in table {table_name}. "
            else: 
                res = f" any type of filters  for column {column} in table {table_name}. "
            
            if column == "name" or column == "shortname":
                res += " search using name and shortname. "
            
            if column == "address" or column == "location":
                res += " search using adress and location. "

            filters.append(res)
            
        return filters

    except Exception as e:
            return [f"erorr while getting filter type : {e}"]
 
@tool
async def get_table_schema(tables: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    input list of tables want to use it query
    use to know tables schema (columns name , data type)
    
    return the list of schemas
    """
    try:
        results = []
        for table in tables:
            if table.lower() not in domain[3]:
                return f" {table} Not part of this agent, use other tables from  {domain[3]}. "
            schm = str(schema[table.lower()]).replace("\\n", " ").replace("\\t", " ")
            results.append(f"schema for table {table.lower()} : {schm}")

        return results
    
    except Exception as e:
        return {"error": {"error while trying to get tables schema": e}}