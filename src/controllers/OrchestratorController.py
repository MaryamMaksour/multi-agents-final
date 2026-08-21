"""The main agent: talks to the user, delegates to the specialists.

It has no database tools of its own - deliberately. An earlier version
carried its own copy of `db_execute` with no table allowlist at all,
which meant the orchestrator could read any table in the database and
route around every domain boundary the sub-agents enforce. Delegation
is the only way it reaches data now, and its Postgres role needs no
SELECT grant on any business table.

Its delegation tools are generated from the agent registry rather than
written out one per domain. Registering an agent is therefore enough to
make the orchestrator able to use it - there is no list here to keep in
sync, and no code change when a spreadsheet agent is added later.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

from langchain_core.messages import BaseMessage, HumanMessage, messages_from_dict, messages_to_dict
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from controllers.BaseController import BaseController
from models.HistoryModel import new_turn_id
from stores.agents.AgentInterface import AgentInterface
from stores.agents.AgentLoop import AgentLoop
from stores.agents.tools import RequestContext, get_request_context
from utils.pipeline import extract_pipeline

logger = logging.getLogger(__name__)


class DelegationInput(BaseModel):
    query: str = Field(
        ...,
        description=(
            "The question for the specialist, phrased so it stands alone - "
            "it cannot see the conversation."
        ),
    )
    offset: int = Field(
        0,
        description="Row to continue from. Use the next_offset from a previous call.",
    )


class ConversationStore:
    """The recent turns of a conversation, shared across replicas.

    Kept in Redis rather than in a process dictionary: with more than
    one replica, a per-process dictionary means the same session sees a
    different history depending on which replica answers.
    """

    def __init__(self, redis, max_messages: int, ttl_seconds: int):
        self.redis = redis
        self.max_messages = max_messages
        self.ttl_seconds = ttl_seconds

    def _key(self, session_id: str) -> str:
        return f"conversation:{session_id}"

    async def get(self, session_id: str) -> List[BaseMessage]:
        raw = await self.redis.get(self._key(session_id))
        if not raw:
            return []
        try:
            return messages_from_dict(json.loads(raw))
        except Exception:
            logger.exception("Could not decode conversation %s; starting fresh", session_id)
            return []

    async def append(self, session_id: str, messages: List[BaseMessage]) -> None:
        if not messages:
            return
        history = await self.get(session_id)
        history.extend(messages)
        history = history[-self.max_messages:]
        await self.redis.set(
            self._key(session_id),
            json.dumps(messages_to_dict(history)),
            ex=self.ttl_seconds,
        )

    async def clear(self, session_id: str) -> None:
        await self.redis.delete(self._key(session_id))

    async def size(self, session_id: str) -> int:
        return len(await self.get(session_id))


class OrchestratorController(BaseController):

    def __init__(
        self,
        config,
        llm,
        agents: Dict[str, AgentInterface],
        template_parser,
        history_model,
        redis,
    ):
        super().__init__(config)
        self.agents = agents
        self.history = history_model
        self.store = ConversationStore(
            redis,
            max_messages=config.MAX_SESSION_MESSAGES,
            ttl_seconds=config.SESSION_TTL_SECONDS,
        )

        tools = [self._delegation_tool(agent) for agent in agents.values()]

        catalog = "\n".join(
            f"  - ask_{agent.key}_agent: {agent.description}" for agent in agents.values()
        ) or "  (none configured)"

        self.system_prompt = template_parser.get(
            "orchestrator", "system_prompt", {"agent_catalog": catalog}
        )

        self.loop = AgentLoop(
            llm=llm,
            tools=tools,
            build_system_prompt=self._system_prompt_for,
            max_iterations=config.AGENT_MAX_ITERATIONS,
            on_tool_call=self._log_tool_call,
        )

    # -- tools --------------------------------------------------------
    def _delegation_tool(self, agent: AgentInterface) -> StructuredTool:
        """Wraps one agent as a tool, from its own key and description."""

        async def call_agent(query: str, offset: int = 0) -> Any:
            context = get_request_context()
            return await agent.ainvoke(
                query=query,
                session_id=context.session_id or "orchestrator",
                offset=offset,
                principal=context.principal,
            )

        return StructuredTool.from_function(
            coroutine=call_agent,
            name=f"ask_{agent.key}_agent",
            description=(
                f"{agent.description}\n"
                "Returns {sql, params, data, total, has_more, next_offset} "
                "or {error}."
            ),
            args_schema=DelegationInput,
        )

    async def _system_prompt_for(self, user_query: str) -> str:
        return self.system_prompt

    async def _log_tool_call(self, **fields) -> None:
        context = get_request_context()
        if not (context.session_id and context.turn_id):
            return
        await self.history.log_tool_call(
            session_id=context.session_id, turn_id=context.turn_id, **fields
        )

    # -- run ----------------------------------------------------------
    async def achat(
        self,
        session_id: str,
        user_input: str,
        principal: Optional[str] = None,
    ) -> Any:
        if not user_input or not str(user_input).strip():
            return {"error": "invalid_user_input"}

        turn_id = new_turn_id()
        context = RequestContext(session_id=session_id, turn_id=turn_id, principal=principal)

        try:
            await self.history.log_user_message(
                session_id=session_id, turn_id=turn_id, user_query=str(user_input)
            )
        except Exception:
            logger.exception("Could not log the user message")

        history = await self.store.get(session_id)
        turn = [HumanMessage(content=str(user_input))]

        started = time.time()
        try:
            result = await self.loop.arun(history + turn, context)
        except Exception as error:
            logger.exception("Orchestrator run failed")
            return {"error": f"chat_failed: {error}"}
        duration = time.time() - started

        messages = result.get("messages") or []
        if not messages:
            return {"error": "agent_returned_no_messages"}

        # Only the user's message and the final answer are kept in the
        # window. Replaying every intermediate tool result would refill
        # the context with rows the model has already summarized.
        await self.store.append(session_id, turn + [messages[-1]])

        trace, shape = extract_pipeline(messages)
        answer = self._final_answer(messages)

        try:
            await self.history.log_assistant_final(
                session_id=session_id, turn_id=turn_id,
                final_answer=answer, trace=trace, shape=shape,
                duration_seconds=duration,
            )
        except Exception:
            logger.exception("Could not log the final answer")

        return answer

    async def areset(self, session_id: str) -> None:
        await self.store.clear(session_id)

    async def history_length(self, session_id: str) -> int:
        return await self.store.size(session_id)

    @staticmethod
    def _final_answer(messages: List[Any]) -> Any:
        content = getattr(messages[-1], "content", None)
        if content is None:
            return {"error": "agent_returned_no_content"}
        if isinstance(content, (dict, list)):
            return content
        text = str(content).strip()
        try:
            return json.loads(text)
        except Exception:
            return {"text": text}
