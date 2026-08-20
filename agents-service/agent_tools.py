
#agent_tools.py
from __future__ import annotations

import os
import httpx

from typing import Any, Dict, Optional

from langchain_core.tools import tool

# -------------------------------------------------------------------
# Config (allow override via env; keep your current defaults)
# -------------------------------------------------------------------
PROPERTY_AGENT_URL = os.getenv("PROPERTY_AGENT_URL", "http://localhost:8001/chat")
HR_AGENT_URL = os.getenv("HR_AGENT_URL", "http://localhost:8002/chat")
CRM_AGENT_URL = os.getenv("CRM_AGENT_URL", "http://localhost:8003/chat")
SALES_PAYMENTS_AGENT_URL = os.getenv("SALES_PAYMENTS_AGENT_URL", "http://localhost:8004/chat")

DEFAULT_TIMEOUT = int(os.getenv("TOOLS_HTTP_TIMEOUT_SECS", "60"))
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
# Note: the orchestrator no longer runs SQL directly (there used to be a
# db_execute/execute_next_cursor pair here that bypassed every sub-agent's
# domain boundary and had no table allowlist of its own - see the audit).
# Pagination continuation happens the way the sub-agent prompts already
# describe: the orchestrator calls the SAME domain tool again with the
# SAME query and the `cursor` it was given, and the sub-agent's own LLM
# (with its own scoped, table-allowlisted db_execute) resumes from there.

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
async def hr_TOOL(
    query: str,
    cursor: Optional[str] = None,
    session_id: str = DEFAULT_SESSION,
    turn_id: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> Any:
    """
    Delegate HR / internal organization queries (employees, heads of sales,
    directors, teams, agents, brokers)
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
        return {"error": "hr_service_error: missing_or_invalid_query"}

    payload = _build_payload(query, cursor, session_id, turn_id)

    try:
        return await _post_json(HR_AGENT_URL, payload, timeout)

    except Exception as e:
        return {"error": f"hr_service_error: {e}"}


@tool
async def crm_TOOL(
    query: str,
    cursor: Optional[str] = None,
    session_id: str = DEFAULT_SESSION,
    turn_id: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> Any:
    """
    Delegate CRM queries: external customers, customer deals, and customer
    request trackers
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
        return {"error": "crm_service_error: missing_or_invalid_query"}

    payload = _build_payload(query, cursor, session_id, turn_id)

    try:
        return await _post_json(CRM_AGENT_URL, payload, timeout)

    except Exception as e:
        return {"error": f"crm_service_error: {e}"}


@tool
async def sales_payments_TOOL(
    query: str,
    cursor: Optional[str] = None,
    session_id: str = DEFAULT_SESSION,
    turn_id: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> Any:
    """
    Delegate sales and payments related queries (bookings, and their
    financial lifecycle: payments, payment splits/plans/terms, installments)
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
        return {"error": "sales_payments_service_error: missing_or_invalid_query"}

    payload = _build_payload(query, cursor, session_id, turn_id)

    try:
        return await _post_json(SALES_PAYMENTS_AGENT_URL, payload, timeout)

    except Exception as e:
        return {"error": f"sales_payments_service_error: {e}"}


# Exports
tools = [property_TOOL, hr_TOOL, crm_TOOL, sales_payments_TOOL]
tools_dict = {tool.name: tool for tool in tools}


def get_tools():
    return tools


def get_tools_dict():
    return tools_dict
