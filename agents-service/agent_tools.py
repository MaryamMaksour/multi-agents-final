
#agent_tools.py
from __future__ import annotations

import os
from typing import Any, Dict, Optional, List, Tuple

import httpx
from langchain_core.tools import tool


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
async def _post_json(url: str, payload: Dict[str, Any], timeout: int) -> Any:
    """Async HTTP POST returning parsed JSON or raising for non-2xx."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=payload, headers={"Content-Type": "application/json"})
        resp.raise_for_status()
        return resp.json()


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


# Exports
tools = [property_TOOL, Organization_TOOL, CRM_TOOL, DEALS_TOOL, SALES_TOOL, PAYMENT_TOOL]  
tools_dict = {tool.name: tool for tool in tools}

def get_tools():
    return tools

def get_tools_dict():
    return tools_dict
