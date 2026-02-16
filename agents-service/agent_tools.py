
#agent_tools.py
from __future__ import annotations

import re
import json
import base64
import os
import zlib
import httpx

from typing import Any, Dict, Optional, Sequence
from venv import logger

from langchain_core.tools import tool

from main.conect_to_DB import get_pool
from main.vector_store import   get_vector

# -------------------------------------------------------------------
# Config (allow override via env; keep your current defaults)
# -------------------------------------------------------------------
PROPERTY_AGENT_URL = os.getenv("PROPERTY_AGENT_URL", "http://localhost:8001/chat")
ORGANIZATION_AGENT_URL = os.getenv("ORGANIZATION_AGENT_URL", "http://localhost:8002/chat")
CRM_AGENT_URL = os.getenv("CRM_AGENT_URL", "http://localhost:8003/chat")
DEALS_AGENT_URL = os.getenv("DEALS_AGENT_URL", "http://localhost:8004/chat")
SALES_AGENT_URL = os.getenv("SALES_AGENT_URL", "http://localhost:8006/chat")
PAYMENT_AGENT_URL = os.getenv("PAYMENT_AGENT_URL", "http://localhost:8007/chat")


DEFAULT_TIMEOUT = int(os.getenv("TOOLS_HTTP_TIMEOUT_SECS", "3600"))
DEFAULT_SESSION = os.getenv("DEFAULT_TOOL_SESSION_ID", "agents:subsession")


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

# --- Minimal query hardening ---
_DISALLOWED = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke)\b",
    flags=re.IGNORECASE,
)
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


def _ensure_select_only(sql: str) :
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

    if "select *" in low or ".*" in low:
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



def _validate_identifier(name: str) -> str:
    """
    Validate SQL identifiers (table/column) to avoid injection.
    Only letters, numbers, and underscore, must start with letter/underscore.
    """
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name or ""):
        return ValueError(f"Invalid identifier: {name!r}")
    return name




async def _post_json(url: str, payload: Dict[str, Any], timeout: int) -> Any:
    """Async HTTP POST returning parsed JSON or raising for non-2xx."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=payload, headers={"Content-Type": "application/json"})
        resp.raise_for_status()
        return resp.json()

def encode_cursor(payload: Dict[str, Any]) -> str:
    s = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    c = zlib.compress(s, level=9)
    return base64.urlsafe_b64encode(c).rstrip(b"=").decode("ascii")

def decode_cursor(cursor: str) -> Dict[str, Any]:
    pad = '=' * (-len(cursor) % 4)
    raw = base64.urlsafe_b64decode(cursor + pad)
    s = zlib.decompress(raw).decode("utf-8")
    return json.loads(s)


def _build_payload(
    query: str,
    cursor: Optional[str],
    session_id: Optional[str],
    turn_id: Optional[str],
) -> Dict[str, Any]:
    """
    Build sub-agent payload. Context carries pagination and tracing IDs.
    """
    return {
        "session_id": session_id or DEFAULT_SESSION,
        "user_input": query,
        "context": {
            "cursor": cursor,
            # pass-through for logging/trace correlation in sub-agent
            "turn_id": turn_id,
        },
    }


# -------------------------------------------------------------------
# Tools (ASYNC)
# -------------------------------------------------------------------

@tool
async def property_TOOL(
    query: str,
    cursor: Optional[str] = None,
    session_id: str = DEFAULT_SESSION,
    turn_id: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> Any:
    """
    Delegate property-related queries (developers, projects, buildings, units)
    Inputs:
      - query: natural language question
      - cursor: next page token (opaque)
    Returns (normalized):
      {
        "sql": [...], # SQL query the sup agent run it
        "params" : [], # paramas for sql 
        "data" [], # rows 
        "has_more": bool,
        "next_cursor": str,
         
      }
    """
    if not isinstance(query, str) or not query.strip():
        return {"error": "property_service_error: missing_or_invalid_query"}

    payload = _build_payload(query, cursor, session_id, turn_id)
 
    try:
        return await _post_json(PROPERTY_AGENT_URL, payload, timeout)
        
    except Exception as e:
        return {"error": f"property_service_error: {e}"}


@tool
async def Organization_TOOL(
    query: str,
    cursor: Optional[str] = None,
    session_id: str = DEFAULT_SESSION,
    turn_id: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> Any:
    """
    Delegate organization-related queries (employees, heads of sales, directors, teams, brokers)
    Inputs:
      - query: natural language question
      - cursor: next page token (opaque)
    Returns (normalized):
      {
        "sql": [...], # SQL query the sup agent run it
        "params" : [], # paramas for sql 
        "data" [], # rows 
        "has_more": bool,
        "next_cursor": str,
         
      }
    """
    if not isinstance(query, str) or not query.strip():
        return {"error": "organization_service_error: missing_or_invalid_query"}

    payload = _build_payload(query, cursor, session_id, turn_id)

    try:
        return await _post_json(ORGANIZATION_AGENT_URL, payload, timeout)
         
    except Exception as e:
        return {"error": f"organization_service_error: {e}"}


@tool
async def CRM_TOOL(
    query: str,
    cursor: Optional[str] = None,
    session_id: str = DEFAULT_SESSION,
    turn_id: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> Any:
    """
    Delegate CRM-related queries.
    Inputs:
      - query: natural language question
      - cursor: next page token (opaque)
    Returns (normalized):
      {
        "sql": [...], # SQL query the sup agent run it
        "params" : [], # paramas for sql 
        "data" [], # rows 
        "has_more": bool,
        "next_cursor": str,
         
      }
    """
    if not isinstance(query, str) or not query.strip():
        return {"error": "CRM_service_error: missing_or_invalid_query"}

    payload = _build_payload(query, cursor, session_id, turn_id)

    try:
        return await _post_json(CRM_AGENT_URL, payload, timeout)
         
    except Exception as e:
        return {"error": f"CRM_service_error: {e}"}

@tool
async def DEALS_TOOL(
    query: str,
    cursor: Optional[str] = None,
    session_id: str = DEFAULT_SESSION,
    turn_id: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> Any:
    """
    Delegate deals-related queries.
    Inputs:
      - query: natural language question
      - cursor: next page token (opaque)
    Returns (normalized):
      {
        "sql": [...], # SQL query the sup agent run it
        "params" : [], # paramas for sql 
        "data" [], # rows 
        "has_more": bool,
        "next_cursor": str,
         
      }
    """
    if not isinstance(query, str) or not query.strip():
        return {"error": "DEALS_service_error: missing_or_invalid_query"}

    payload = _build_payload(query, cursor, session_id, turn_id)

    try:
        return await _post_json(DEALS_AGENT_URL, payload, timeout)
         
    except Exception as e:
        return {"error": f"DEALS_service_error: {e}"}



@tool
async def SALES_TOOL(
    query: str,
    cursor: Optional[str] = None,
    session_id: str = DEFAULT_SESSION,
    turn_id: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> Any:
    """
    Delegate sales-related queries.
    Inputs:
      - query: natural language question
      - cursor: next page token (opaque)
    Returns (normalized):
      {
        "sql": [...], # SQL query the sup agent run it
        "params" : [], # paramas for sql 
        "data" [], # rows 
        "has_more": bool,
        "next_cursor": str,
         
      }
    """
    if not isinstance(query, str) or not query.strip():
        return {"error": "SALES_service_error: missing_or_invalid_query"}

    payload = _build_payload(query, cursor, session_id, turn_id)

    try:
        return await _post_json(SALES_AGENT_URL, payload, timeout)
         
    except Exception as e:
        return {"error": f"SALES_service_error: {e}"}

@tool
async def PAYMENT_TOOL(
    query: str,
    cursor: Optional[str] = None,
    session_id: str = DEFAULT_SESSION,
    turn_id: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> Any:
    """
    Delegate payment-related queries.
    Inputs:
      - query: natural language question
      - cursor: next page token (opaque)
    Returns (normalized):
      {
        "sql": [...], # SQL query the sup agent run it
        "params" : [], # paramas for sql 
        "data" [], # rows 
        "has_more": bool,
        "next_cursor": str,
         
      }
    """
    if not isinstance(query, str) or not query.strip():
        return {"error": "PAYMENT_service_error: missing_or_invalid_query"}

    payload = _build_payload(query, cursor, session_id, turn_id)

    try:
        return await _post_json(PAYMENT_AGENT_URL, payload, timeout)
         
    except Exception as e:
        return {"error": f"PAYMENT_service_error: {e}"}

async def db_execute(   query: str,
                        params: Sequence[Any],
                        offset: int,
                        count_query: str,
                        count_params: Sequence[Any],
                        cursor: Optional[str] = None ,
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
            return f"error limit $n should be in the query in this shape  limit &n offset &m, and params = [..,&n_value, &m_value]"
        
        if "offset $" not in query:
            return f"error offset $n should be in the query in this shape  limit &n offset &m, and params = [..,&n_value, &m_value]"
        
        if len(params) >= 2:
            if int(params[-2]) > 100:
                return f"error, limit should be less than 100"
        else:
            return f"error offset and limit should be in the query in this shape  limit &n offset &m, and params = [..,&n_value, &m_value]"

        
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
                print("rows", rows)
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
                        "resolved_params": resolved_params,
                        "query": query
                    })

             
                return {"rows": data, 
                        "row_count": total, 
                        "has_more": has_more,
                        "next_cursor": next_cursor}
              
              except Exception as e:
                  return f"error {e}"
                    

    except Exception as e:

        error_msg = str(e)


        logger.exception(f"db_execute failed + {error_msg}")
        return {"error": error_msg}
    
@tool
async def execute_next_cursor(cursor: str) -> Dict[str, Any]:
    """
    use this tool insed of re call the agent
    Helper tool to execute the next page of results based on a cursor.
    Decodes the cursor to get the next query and offset, then calls db_execute.

    input: cursor (str): The encoded cursor returned from tool agent.
     return dict{{"rows": all data from query, 
                        "row_count": result from count_query, 
                        "has_more": has_more if total > limit+ offset,
                        "next_cursor": next_cursor} } 
    """
    try:
        state = decode_cursor(cursor)
        query = state["query"]
        offset = state["offset"]
        params = state["resolved_params"]
        params[-1] = offset  # Assuming the last parameter is the offset for pagination

     
        # For count_query and count_params, you would also need to reconstruct them based on your application's needs
        count_query = ""  # Placeholder
        count_params = []  # Placeholder

        return await db_execute(query=query, params=params, offset=offset, count_query=count_query, count_params=count_params, cursor=None)

    except Exception as e:
        logger.exception("execute_next_cursor failed")
        return {"error": str(e)}      
    
    
# Exports
tools = [property_TOOL, Organization_TOOL, CRM_TOOL, DEALS_TOOL, SALES_TOOL, PAYMENT_TOOL, execute_next_cursor]  
tools_dict = {tool.name: tool for tool in tools}

def get_tools():
    return tools

def get_tools_dict():
    return tools_dict
