"""The orchestrator's delegation, and the registry that drives it."""
import json

import pytest
from langchain_core.messages import AIMessage

from controllers import OrchestratorController
from stores.agents import AgentProviderFactory
from stores.agents.prompts import TemplateParser
from stores.agents.specs import AGENT_REGISTRY

pytestmark = pytest.mark.asyncio


class FakeRedis:
    def __init__(self):
        self.store = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self.store[key] = value

    async def delete(self, key):
        self.store.pop(key, None)


class FakeHistory:
    def __init__(self):
        self.entries = []

    async def log_user_message(self, **fields):
        self.entries.append(("user", fields))

    async def log_assistant_final(self, **fields):
        self.entries.append(("final", fields))

    async def log_tool_call(self, **fields):
        self.entries.append(("tool", fields))


class RecordingLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.bound_tools = []

    def bind_tools(self, tools):
        self.bound_tools = tools
        return self

    async def ainvoke(self, messages):
        self.system_prompt = messages[0].content
        return self.responses.pop(0) if self.responses else AIMessage(content="{}")


def _build(settings, llm, agents):
    return OrchestratorController(
        config=settings, llm=llm, agents=agents,
        template_parser=TemplateParser(),
        history_model=FakeHistory(), redis=FakeRedis(),
    )


def _remote_agents(settings, monkeypatch, routes):
    monkeypatch.setattr(
        settings, "SUB_AGENT_URLS", [f"{k}={v}" for k, v in routes.items()], raising=False
    )
    return AgentProviderFactory(config=settings, pg_client=None).create_all_remote()


async def test_delegation_tools_come_from_the_registry(settings, monkeypatch):
    """Registering an agent is enough - the orchestrator has no list of its own."""
    agents = _remote_agents(settings, monkeypatch, {
        "hr": "http://agent-hr:8002", "crm": "http://agent-crm:8003",
    })
    llm = RecordingLLM([])
    controller = _build(settings, llm, agents)

    assert sorted(tool.name for tool in llm.bound_tools) == ["ask_crm_agent", "ask_hr_agent"]
    for key in AGENT_REGISTRY:
        assert f"ask_{key}_agent" in controller.system_prompt


async def test_an_unregistered_route_is_skipped_not_fatal(settings, monkeypatch):
    agents = _remote_agents(settings, monkeypatch, {
        "hr": "http://agent-hr:8002", "ghost": "http://nowhere:9999",
    })
    assert sorted(agents) == ["hr"]


async def test_orchestrator_has_no_database_tools(settings, monkeypatch):
    """It reaches data only by delegating.

    An earlier orchestrator carried its own copy of db_execute with no
    table allowlist, which let it read any table in the database and
    bypass every domain boundary the sub-agents enforce.
    """
    agents = _remote_agents(settings, monkeypatch, {"hr": "http://agent-hr:8002"})
    llm = RecordingLLM([])
    _build(settings, llm, agents)

    names = {tool.name for tool in llm.bound_tools}
    assert all(name.startswith("ask_") and name.endswith("_agent") for name in names)


async def test_delegation_reaches_the_agent_with_the_session(settings, monkeypatch):
    calls = []

    class SpyAgent:
        key = "hr"
        description = "hr data"

        async def ainvoke(self, query, session_id, offset=0, principal=None):
            calls.append({"query": query, "session_id": session_id,
                          "offset": offset, "principal": principal})
            return {"data": [{"id": 1}], "total": 1}

        async def health(self):
            return {"agent": "hr", "status": "ok"}

    llm = RecordingLLM([
        AIMessage(content="", tool_calls=[{
            "name": "ask_hr_agent",
            "args": {"query": "how many active employees", "offset": 0},
            "id": "c1", "type": "tool_call",
        }]),
        AIMessage(content=json.dumps({"text": "There are 42."})),
    ])
    controller = _build(settings, llm, {"hr": SpyAgent()})

    answer = await controller.achat("session-1", "how many active employees?", principal="alice")

    assert answer == {"text": "There are 42."}
    assert calls[0]["query"] == "how many active employees"
    assert calls[0]["session_id"] == "session-1"
    # Identity is threaded through delegation, ready for row-level security.
    assert calls[0]["principal"] == "alice"


async def test_only_the_question_and_answer_stay_in_the_window(settings, monkeypatch):
    """Intermediate tool results are not replayed into the next turn.

    Keeping them would refill the context with rows the model has
    already summarized, one turn after another.
    """
    class QuietAgent:
        key = "hr"
        description = "hr data"

        async def ainvoke(self, **_kwargs):
            return {"data": [{"id": i} for i in range(50)]}

        async def health(self):
            return {"agent": "hr", "status": "ok"}

    llm = RecordingLLM([
        AIMessage(content="", tool_calls=[{
            "name": "ask_hr_agent", "args": {"query": "q", "offset": 0},
            "id": "c1", "type": "tool_call",
        }]),
        AIMessage(content=json.dumps({"text": "done"})),
    ])
    controller = _build(settings, llm, {"hr": QuietAgent()})

    await controller.achat("session-2", "q")
    assert await controller.history_length("session-2") == 2


async def test_reset_clears_the_window(settings):
    llm = RecordingLLM([AIMessage(content=json.dumps({"text": "hi"}))])
    controller = _build(settings, llm, {})

    await controller.achat("session-3", "hello")
    assert await controller.history_length("session-3") > 0

    await controller.areset("session-3")
    assert await controller.history_length("session-3") == 0


async def test_empty_input_is_refused(settings):
    controller = _build(settings, RecordingLLM([]), {})
    assert await controller.achat("s", "   ") == {"error": "invalid_user_input"}
