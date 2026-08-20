"""A domain agent that answers by querying its own tables.

This is the only implementation behind hr and crm - and behind any SQL
domain added later. What makes it "the HR agent" is the spec it was
built with: a table allowlist, a history table, and three prompt
fragments. Nothing in this file names a domain.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage

from models.HistoryModel import new_turn_id
from utils.pipeline import extract_pipeline

from ..AgentInterface import AgentInterface
from ..AgentLoop import AgentLoop
from ..tools import RequestContext, build_sql_toolset

logger = logging.getLogger(__name__)


class SQLDomainAgent(AgentInterface):

    def __init__(
        self,
        spec,
        config,
        llm,
        embed_text,
        pg_client,
        history_model,
        memory_model,
        template_parser,
    ):
        self.spec = spec
        self.key = spec.key
        self.description = spec.tool_description
        self.config = config
        self.embed_text = embed_text
        self.history = history_model
        self.memory = memory_model

        self.system_prompt = template_parser.get(
            "sql_agent", "system_prompt",
            {
                "domain_label": spec.description,
                "relations": spec.relations,
                "normalizations": spec.normalizations,
                "defaults": spec.defaults,
            },
        )

        tools = build_sql_toolset(
            allowed_tables=spec.tables,
            table_notes=spec.table_notes,
            pg_client=pg_client,
            embed_text=embed_text,
            config=config,
            log_sql=history_model.log_sql,
        )

        self.loop = AgentLoop(
            llm=llm,
            tools=tools,
            build_system_prompt=self._system_prompt_for,
            max_iterations=config.AGENT_MAX_ITERATIONS,
            on_tool_call=self._log_tool_call,
        )

    # -- prompt -------------------------------------------------------
    async def _system_prompt_for(self, user_query: str) -> str:
        """The domain prompt, plus worked examples when memory has any.

        The examples carry each past turn's reasoning - which tools ran,
        with what SQL - and never the rows those calls returned. That is
        the part that teaches; replaying the data would put one user's
        results into another user's prompt for no gain.
        """
        if not (self.config.MEMORY_ENABLED and user_query):
            return self.system_prompt

        try:
            vector = self._vector_literal(await self.embed_text(user_query))
            examples = await self.memory.get_examples(vector)
        except Exception:
            logger.exception("Memory enrichment failed; continuing without examples")
            return self.system_prompt

        if not examples:
            return self.system_prompt

        import json
        return (
            f"{self.system_prompt}\n\n"
            "WORKED EXAMPLES\n"
            "How similar questions were handled before. Follow the approach, "
            "not the specifics - these carry no data, only the steps taken.\n"
            f"{json.dumps(examples, ensure_ascii=False, default=str)}"
        )

    @staticmethod
    def _vector_literal(vector: List[float]) -> str:
        return "[" + ",".join(str(float(value)) for value in vector) + "]"

    # -- logging ------------------------------------------------------
    async def _log_tool_call(self, **fields) -> None:
        from ..tools import get_request_context
        context = get_request_context()
        if not (context.session_id and context.turn_id):
            return
        await self.history.log_tool_call(
            session_id=context.session_id, turn_id=context.turn_id, **fields
        )

    # -- run ----------------------------------------------------------
    async def ainvoke(
        self,
        query: str,
        session_id: str,
        offset: int = 0,
        principal: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not query or not str(query).strip():
            return {"error": "invalid_user_input"}

        turn_id = new_turn_id()
        context = RequestContext(session_id=session_id, turn_id=turn_id, principal=principal)

        embedding = None
        try:
            embedding = self._vector_literal(await self.embed_text(str(query)))
        except Exception:
            logger.exception("Could not embed the question; it will not be recallable")

        try:
            await self.history.log_user_message(
                session_id=session_id, turn_id=turn_id,
                user_query=str(query), embedding=embedding,
                context={"offset": offset},
            )
        except Exception:
            logger.exception("Could not log the user message")

        prompt = str(query) if not offset else f"{query}\n\n(Continue from offset {offset}.)"

        started = time.time()
        try:
            result = await self.loop.arun([HumanMessage(content=prompt)], context)
        except Exception as error:
            logger.exception("Agent run failed")
            return {"error": f"agent_failed: {error}"}
        duration = time.time() - started

        messages = result.get("messages") or []
        if not messages:
            return {"error": "agent_returned_no_messages"}

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

    @staticmethod
    def _final_answer(messages: List[Any]) -> Any:
        import json
        content = getattr(messages[-1], "content", None)
        if content is None:
            return {"error": "agent_returned_no_content"}
        if isinstance(content, (dict, list)):
            return content
        text = str(content).strip()
        try:
            parsed = json.loads(text)
        except Exception:
            return {"text": text}
        return parsed
