# agent_common/rag_agent.py
#
# The LangGraph tool-calling loop was byte-for-byte identical across all
# 6 sub-agent services before this was extracted, differing only in a
# label string used when an invalid tool name is called. build_rag_agent()
# is that same implementation, parameterized by the domain's tools/prompt
# instead of copy-pasted.
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable, Dict, List, Sequence, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, StateGraph
from operator import add as add_messages

from main.llm import get_llm

logger = logging.getLogger(__name__)


class AgentState(TypedDict):
    messages: Sequence[BaseMessage]
    did_memory_enrichment: bool  # semantic search runs only once per user query


def _last_user_text(state: AgentState) -> str:
    for msg in reversed(state["messages"]):
        if isinstance(msg, HumanMessage):
            return str(msg.content)
    return " ".join(str(getattr(m, "content", "")) for m in state["messages"])


def build_rag_agent(
    tools: list,
    tools_dict: dict,
    system_prompt: str,
    domain_label: str,
    get_memory: Callable[[str], Awaitable[list]],
    log_tool_call: Callable[..., Awaitable[None]],
) -> Callable[[List[BaseMessage]], Awaitable[Dict[str, Any]]]:
    """
    Builds one domain's LangGraph tool-calling agent. Returns an async
    `run_agent(messages) -> {"messages": [...]}` callable - everything
    else (state machine, tool dispatch, memory-enrichment) is identical
    across domains and lives here once.
    """
    llm = get_llm().bind_tools(tools)

    def should_continue(state: AgentState) -> bool:
        last = state["messages"][-1]
        return hasattr(last, "tool_calls") and bool(last.tool_calls)

    async def call_llm(state: AgentState) -> AgentState:
        system_prompt_new = system_prompt
        query_text = _last_user_text(state)
        if not state.get("did_memory_enrichment", False):
            try:
                if query_text:
                    examples = []
                    semantic_results = await get_memory(query_text)
                    for res in semantic_results:
                        examples.append(str(res))

                    if examples:
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

    async def _invoke_one_tool(call: Dict[str, Any]) -> ToolMessage:
        tool_name = call.get("name")
        args = dict(call.get("args") or {})

        session_id = args.get("session_id", "")
        turn_id = args.get("turn_id", "")

        if tool_name not in tools_dict:
            err = {
                "error": "Incorrect tool name. Please select a tool from the available tools list.",
                "tool_name": tool_name,
            }

            if session_id and turn_id:
                await log_tool_call(
                    session_id=session_id,
                    turn_id=turn_id,
                    tool_name=f"{tool_name} {domain_label}",
                    tool_args=args,
                    tool_result=err,
                    tool_call_id=call.get("id"),
                    error=err["error"],
                )

            return ToolMessage(
                tool_call_id=call.get("id"),
                name=str(tool_name),
                content=json.dumps(err, ensure_ascii=False),
            )

        result: Any = ""
        error_msg = ""

        try:
            result = await tools_dict[tool_name].ainvoke(args)
        except Exception as e:
            logger.exception("Tool call failed: %s", tool_name)
            error_msg = str(e)
            result = {"error": str(e), "tool_name": tool_name}

        if session_id and turn_id:
            try:
                await log_tool_call(
                    session_id=session_id,
                    turn_id=turn_id,
                    tool_name=tool_name,
                    tool_args=args,
                    tool_result=result,
                    tool_call_id=call.get("id"),
                    error=error_msg,
                )
            except Exception:
                pass

        return ToolMessage(
            tool_call_id=call.get("id"),
            name=tool_name,
            content=json.dumps(result, ensure_ascii=False),
        )

    async def take_action(state: AgentState) -> AgentState:
        tool_calls = state["messages"][-1].tool_calls
        tool_messages = await asyncio.gather(*(_invoke_one_tool(call) for call in tool_calls))
        return {"messages": tool_messages}

    graph = StateGraph(AgentState)
    graph.add_node("llm", call_llm)
    graph.add_node("tools", take_action)
    graph.add_conditional_edges("llm", should_continue, {True: "tools", False: END})
    graph.add_edge("tools", "llm")
    graph.set_entry_point("llm")

    compiled_graph = graph.compile()

    async def run_agent(message: List[BaseMessage]):
        state = {
            "messages": message,
            "did_memory_enrichment": False,
        }
        return await compiled_graph.ainvoke(state)

    return run_agent
