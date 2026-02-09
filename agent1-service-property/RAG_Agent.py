
# RAG_Agent.py
from __future__ import annotations

from typing import TypedDict, Annotated, Sequence, Dict, Any
import json
import asyncio
import logging

from langgraph.graph import StateGraph, END
from operator import add as add_messages
from langchain_core.messages import BaseMessage, SystemMessage, ToolMessage, HumanMessage

from main.llm import get_llm
from .agent_tools import get_tools, get_tools_dict
from .prompt import system_prompt
from .history_repo_1 import log_tool_call, get_memory


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
# Agent State
# ============================================================

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    did_memory_enrichment: bool #semantic search runs only once per user query
    

# ============================================================
# Control Logic
# ============================================================

def should_continue(state: AgentState) -> bool:
    last = state["messages"][-1]
    return hasattr(last, "tool_calls") and bool(last.tool_calls)

# ============================================================
# LLM Node
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
# Tool Executor (GENERIC, SAFE)
# ============================================================

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
                tool_name=str(tool_name) + " propoty ",
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
    result = ""
    error_msg = ""
    
    try:
        #print("From RAG Agent _invoke one tool")
        print(f"colling tool {tool_name} with args {args}")
        result = await tools_dict[tool_name].ainvoke(args)
        print(f"result of tool: {result}")

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
        except:
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

# ============================================================
# Graph Wiring
# ============================================================

graph = StateGraph(AgentState)
graph.add_node("llm", call_llm)
graph.add_node("tools", take_action)
graph.add_conditional_edges("llm", should_continue, {True: "tools", False: END})
graph.add_edge("tools", "llm")
graph.set_entry_point("llm")

rag_agent = graph.compile()

# ============================================================
# Public Runner
# ============================================================

async def run_agent(message: list[BaseMessage]):
    
    state = {
        "messages": message,
        "did_memory_enrichment": False,
    }

    return await rag_agent.ainvoke(state)
