"""The shared tool-calling loop."""
import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from stores.agents import AgentLoop
from stores.agents.tools import RequestContext

pytestmark = pytest.mark.asyncio


class ScriptedLLM:
    """Replays a fixed list of responses and records what it was sent."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def bind_tools(self, tools):
        self.bound_tools = tools
        return self

    async def ainvoke(self, messages):
        self.calls.append(list(messages))
        return self.responses.pop(0) if self.responses else AIMessage(content="{}")


def _tool_call(name, args, call_id):
    return {"name": name, "args": args, "id": call_id, "type": "tool_call"}


async def _controller(llm, tools, max_iterations=5, on_tool_call=None):
    async def prompt(_query):
        return "system"
    return AgentLoop(llm, list(tools.values()), prompt, max_iterations, on_tool_call)


async def test_tool_results_are_fed_back_to_the_model(hr_tools):
    """The reducer on `messages` is what makes the loop work at all.

    Without it each node's return replaced the message list instead of
    appending, so on its second turn the model could no longer see the
    tool call it had just made or the result it came back with.
    """
    llm = ScriptedLLM([
        AIMessage(content="", tool_calls=[_tool_call("get_table_schema", {"tables": ["employees"]}, "c1")]),
        AIMessage(content=json.dumps({"data": []})),
    ])
    controller = await _controller(llm, hr_tools)

    result = await controller.arun(
        [HumanMessage(content="list employees")], RequestContext("s", "t")
    )

    assert len(llm.calls) == 2
    second_turn = llm.calls[1]
    assert any(getattr(m, "tool_call_id", None) == "c1" for m in second_turn)
    assert len(result["messages"]) >= 4


async def test_unknown_tool_is_reported_to_the_model(hr_tools):
    llm = ScriptedLLM([
        AIMessage(content="", tool_calls=[_tool_call("no_such_tool", {}, "c1")]),
        AIMessage(content="{}"),
    ])
    controller = await _controller(llm, hr_tools)
    result = await controller.arun([HumanMessage(content="x")], RequestContext("s", "t"))

    tool_message = [m for m in result["messages"] if getattr(m, "tool_call_id", None) == "c1"][0]
    payload = json.loads(tool_message.content)
    assert "error" in payload
    # Telling it which tools exist is what lets it recover in one turn.
    assert "available_tools" in payload


async def test_loop_is_bounded(hr_tools):
    """A model that will not stop calling tools must not spin forever."""
    class NeverFinishes(ScriptedLLM):
        async def ainvoke(self, messages):
            self.calls.append(list(messages))
            return AIMessage(content="", tool_calls=[_tool_call("get_tables", {}, "x")])

    controller = await _controller(NeverFinishes([]), hr_tools, max_iterations=3)
    result = await controller.arun([HumanMessage(content="x")], RequestContext("s", "t"))
    assert result["iterations"] <= 3


async def test_every_tool_call_is_logged(hr_tools):
    logged = []

    async def on_tool_call(**fields):
        logged.append(fields)

    llm = ScriptedLLM([
        AIMessage(content="", tool_calls=[_tool_call("get_tables", {}, "c1")]),
        AIMessage(content="{}"),
    ])
    controller = await _controller(llm, hr_tools, on_tool_call=on_tool_call)
    await controller.arun([HumanMessage(content="x")], RequestContext("s", "t"))

    assert [entry["tool_name"] for entry in logged] == ["get_tables"]


async def test_a_failing_logger_never_breaks_a_turn(hr_tools):
    async def broken_logger(**_fields):
        raise RuntimeError("audit database is down")

    llm = ScriptedLLM([
        AIMessage(content="", tool_calls=[_tool_call("get_tables", {}, "c1")]),
        AIMessage(content=json.dumps({"ok": True})),
    ])
    controller = await _controller(llm, hr_tools, on_tool_call=broken_logger)
    result = await controller.arun([HumanMessage(content="x")], RequestContext("s", "t"))

    assert json.loads(result["messages"][-1].content) == {"ok": True}
