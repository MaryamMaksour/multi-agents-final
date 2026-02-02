
# RAG_Agent.py (FINAL V1 WITH ASYNC + PAGINATION)

from __future__ import annotations

import json
import asyncio
import logging
from typing import TypedDict, Annotated, Sequence, Dict, Any
from operator import add as add_messages

from langgraph.graph import StateGraph, END
from langchain_core.messages import BaseMessage, SystemMessage, ToolMessage, HumanMessage

from main.llm import get_llm
from .agent_tools import get_tools, get_tools_dict
from .prompt import system_prompt
from main.history_repo import log_tool_call, get_memory
from main.config import MAX_PAGES_PER_TOOL   

logger = logging.getLogger(__name__)

def _last_user_text(state: AgentState) -> str:
    for msg in reversed(state["messages"]):
        if isinstance(msg, HumanMessage):
            return str(msg.content)
    return " ".join(str(getattr(m, "content", "")) for m in state["messages"])

# ============================================================
# LLM + Tools
# ============================================================

llm = get_llm().bind_tools(get_tools())
tools_dict = get_tools_dict()


# ============================================================
# Agent State (MATCHING V0)
# ============================================================

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    pagination: Dict[str, Dict[str, Any]]


# ============================================================
# Control Logic (MATCHING V0)
# ============================================================

def should_continue(state: AgentState) -> bool:
    """Stop only when LLM has no tool calls.
       Pagination DOES NOT stop the graph (same as V0 actual behavior)."""
    last = state["messages"][-1]
    return hasattr(last, "tool_calls") and bool(last.tool_calls)


# ============================================================
# LLM Node (ASYNC)
# ============================================================

async def call_llm(state: AgentState) -> AgentState:
    system_prompt_new = system_prompt
    # do semantic search
    query_text = _last_user_text(state)
    if not state.get("did_memory_enrichment", False):

        try:
            if query_text:
                examples = []
                semantic_results = await get_memory(query_text)
                for res in semantic_results:
                        #print(make_base_message(str(res)))
                        examples.append(str(res))

                if examples:
                    '''print("_______________________________________________________")
                    print("list(state['messages'])", query_text)
                    print("_______________________________________________________")
                    print("examples: ", examples)
                    print("_______________________________________________________")'''
                    system_prompt_new += " Some examples: " + str(examples)

        
        except Exception:
                # Don't block the main request if memory lookup fails
                logger.exception("get_memory failed; continuing without examples")
                system_prompt_new = system_prompt


    messages = [SystemMessage(content=str(system_prompt_new))] + list(state["messages"]) 
    response = await llm.ainvoke(messages)
    return {
            "messages": [response],
            "did_memory_enrichment": True,
            }


# ============================================================
# TOOL EXECUTION WITH PAGINATION (MATCHING V0)
# ============================================================

async def _invoke_one_tool(call: Dict[str, Any], pagination: Dict[str, Any]) -> ToolMessage:
    tool_name = call.get("name")
    args = dict(call.get("args") or {})

    session_id = args.get("session_id", "")
    turn_id = args.get("turn_id", "")

    # Validate tool name
    if tool_name not in tools_dict:
        error = {
            "error": "Incorrect tool name. Please select a tool from the available tools.",
            "tool_name": tool_name
        }

        if session_id and turn_id:
            await log_tool_call(
                session_id=session_id,
                turn_id=turn_id,
                tool_name=str(tool_name),
                tool_args=args,
                tool_result=error,
                tool_call_id=call.get("id"),
                error=error["error"]
            )

        return ToolMessage(
            tool_call_id=call.get("id"),
            name=str(tool_name),
            content=json.dumps(error)
        )

    # ======================================================
    # PAGINATION LOGIC (RESTORED FROM V0)
    # ======================================================

    page_info = pagination.get(tool_name)

    # Inject cursor only when same query continues
    if page_info and page_info.get("next_cursor") and page_info.get("query") == args.get("query"):
        args["cursor"] = page_info["next_cursor"]

    # Enforce max pages (optional — acting like V0 design)
    if page_info and page_info.get("pages_fetched", 0) >= MAX_PAGES_PER_TOOL:
        result = {
            "error": f"Pagination limit reached: MAX_PAGES_PER_TOOL={MAX_PAGES_PER_TOOL}",
            "tool_name": tool_name,
            "has_more": False
        }
    else:
        # True async invocation
        try:
            print(f"[TOOL] Calling {tool_name} with args: {args}")
            result = await tools_dict[tool_name].ainvoke(args)
            print(f"[TOOL RESULT] {tool_name}: {result}")

        except Exception as e:
            logger.exception("Tool failed: %s", tool_name)
            result = {"error": str(e), "tool_name": tool_name}

    # Update pagination state (matching V0)
    if isinstance(result, dict) and "has_more" in result:
        pagination[tool_name] = {
            "query": args.get("query"),
            "has_more": result.get("has_more", False),
            "next_cursor": result.get("next_cursor"),
            "pages_fetched": pagination.get(tool_name, {}).get("pages_fetched", 0) + 1,
        }

    # Log tool call
    if session_id and turn_id:
        await log_tool_call(
            session_id=session_id,
            turn_id=turn_id,
            tool_name=tool_name,
            tool_args=args,
            tool_result=result,
            tool_call_id=call.get("id"),
            error=result.get("error", "")
        )

    return ToolMessage(
        tool_call_id=call.get("id"),
        name=tool_name,
        content=json.dumps(result)
    )


# ============================================================
# TOOL NODE (ASYNC + PAGINATION)
# ============================================================

async def take_action(state: AgentState) -> AgentState:
    tool_calls = state["messages"][-1].tool_calls
    pagination = state.get("pagination", {})

    tool_messages = await asyncio.gather(
        *(_invoke_one_tool(call, pagination) for call in tool_calls)
    )

    return {"messages": tool_messages, "pagination": pagination}


# ============================================================
# GRAPH
# ============================================================

graph = StateGraph(AgentState)

graph.add_node("llm", call_llm)
graph.add_node("tools", take_action)

graph.add_conditional_edges("llm", should_continue, {True: "tools", False: END})
graph.add_edge("tools", "llm")

graph.set_entry_point("llm")

rag_agent = graph.compile()


# ============================================================
# PUBLIC RUNNER
# ============================================================

async def run_agent(history: list[BaseMessage]):
    return await rag_agent.ainvoke({
        "messages": history,
        "pagination": {}
    })
