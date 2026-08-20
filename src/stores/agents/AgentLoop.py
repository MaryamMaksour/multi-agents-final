"""The tool-calling loop, shared by every agent in the system.

One LangGraph state machine: ask the model, run whatever tools it asked
for, feed the results back, repeat until it answers. Both the domain
agents and the orchestrator run on this - they differ in which tools
they are given and which prompt they are built with, not in how they
loop.

It lives under stores/ rather than controllers/ because it is
generic machinery, not business logic: it knows how to run a
tool-calling loop and nothing about any domain. Controllers depend on
stores, never the other way round, and the providers that build agents
need this - putting it in controllers/ made stores import controllers
and closed a cycle.

Three fixes over the previous copy of this loop:

- `messages` is annotated with an `add_messages` reducer. Without one,
  each node's return *replaced* the state's message list instead of
  appending to it, so the model lost sight of its own tool calls
  between iterations.
- The loop is bounded. A model that keeps calling tools used to spin
  until something else timed out; it now stops and says so.
- Session and turn identity reach the tools through a context variable
  rather than through tool arguments the model has to copy. Arguments
  the model writes are arguments a prompt injection can rewrite, and
  when the model forgot them the call simply went unlogged.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Annotated, Any, Awaitable, Callable, Dict, List, Optional, Sequence, TypedDict

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from .tools import RequestContext, reset_request_context, set_request_context

logger = logging.getLogger(__name__)


class AgentState(TypedDict):
    # add_messages appends; without it every node overwrote the history.
    messages: Annotated[Sequence[BaseMessage], add_messages]
    iterations: int


class AgentLoop:

    def __init__(
        self,
        llm,
        tools: List[Any],
        build_system_prompt: Callable[[str], Awaitable[str]],
        max_iterations: int = 12,
        on_tool_call: Optional[Callable[..., Awaitable[None]]] = None,
    ):
        """
        build_system_prompt  async (user_query) -> system prompt. Async
                             because it may look up semantic examples.
        on_tool_call         async logging hook; never allowed to break a turn.
        """
        self.tools = tools
        self.tools_by_name = {tool.name: tool for tool in tools}
        self.build_system_prompt = build_system_prompt
        self.max_iterations = max_iterations
        self.on_tool_call = on_tool_call

        self.llm = llm.bind_tools(tools)
        self.graph = self._build_graph()

    # -- graph --------------------------------------------------------
    def _build_graph(self):
        graph = StateGraph(AgentState)
        graph.add_node("llm", self._call_llm)
        graph.add_node("tools", self._call_tools)
        graph.add_conditional_edges(
            "llm", self._should_continue, {True: "tools", False: END}
        )
        graph.add_edge("tools", "llm")
        graph.set_entry_point("llm")
        return graph.compile()

    def _should_continue(self, state: AgentState) -> bool:
        if state.get("iterations", 0) >= self.max_iterations:
            logger.warning("Agent hit the %d-iteration ceiling", self.max_iterations)
            return False
        last = state["messages"][-1]
        return bool(getattr(last, "tool_calls", None))

    @staticmethod
    def _last_user_text(state: AgentState) -> str:
        for message in reversed(state["messages"]):
            if isinstance(message, HumanMessage):
                return str(message.content)
        return ""

    async def _call_llm(self, state: AgentState) -> Dict[str, Any]:
        system_prompt = await self.build_system_prompt(self._last_user_text(state))
        messages = [SystemMessage(content=system_prompt)] + list(state["messages"])
        response = await self.llm.ainvoke(messages)
        return {"messages": [response], "iterations": state.get("iterations", 0) + 1}

    async def _call_tools(self, state: AgentState) -> Dict[str, Any]:
        calls = state["messages"][-1].tool_calls
        results = await asyncio.gather(*(self._invoke_tool(call) for call in calls))
        return {"messages": list(results)}

    async def _invoke_tool(self, call: Dict[str, Any]) -> ToolMessage:
        name = call.get("name")
        args = dict(call.get("args") or {})

        if name not in self.tools_by_name:
            payload = {
                "error": f"There is no tool named {name!r}.",
                "available_tools": sorted(self.tools_by_name),
            }
            await self._log_tool_call(name, args, payload, call.get("id"), payload["error"])
            return ToolMessage(
                tool_call_id=call.get("id"),
                name=str(name),
                content=json.dumps(payload, ensure_ascii=False),
            )

        error_message = ""
        try:
            result = await self.tools_by_name[name].ainvoke(args)
        except Exception as error:
            logger.exception("Tool %s failed", name)
            error_message = str(error)
            result = {"error": error_message, "tool_name": name}

        await self._log_tool_call(name, args, result, call.get("id"), error_message)

        return ToolMessage(
            tool_call_id=call.get("id"),
            name=name,
            content=json.dumps(result, ensure_ascii=False, default=str),
        )

    async def _log_tool_call(self, name, args, result, call_id, error) -> None:
        if self.on_tool_call is None:
            return
        try:
            await self.on_tool_call(
                tool_name=name,
                tool_args=args,
                tool_result=result,
                tool_call_id=call_id,
                error=error or None,
            )
        except Exception:
            logger.exception("Tool-call logging failed")

    # -- run ----------------------------------------------------------
    async def arun(
        self,
        messages: List[BaseMessage],
        context: RequestContext,
    ) -> Dict[str, Any]:
        """Runs the loop with `context` visible to every tool it calls."""
        token = set_request_context(context)
        try:
            return await self.graph.ainvoke({"messages": messages, "iterations": 0})
        finally:
            reset_request_context(token)
