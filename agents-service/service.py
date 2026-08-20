
# service.py
from __future__ import annotations

from typing import Any, Dict, Optional, List
import json
import os
import logging
import time

from langchain_core.messages import BaseMessage, messages_from_dict, messages_to_dict

from openinference.instrumentation.langchain import LangChainInstrumentor
import phoenix as px
from phoenix.otel import register

from .running_agent import run_agent_with_history, make_human_message

from helpers.config import MAX_SESSION_MESSAGES, CONTEXT_MESSAGES_SENT
from stores.cache import get_redis
from .history_repo import new_turn_id, log_user_message, log_assistant_final
from utils.pipeline_utils import extract_pipeline_main

logger = logging.getLogger(__name__)
'''
# ------------------------------------------------------------
# TRACING (Phoenix / OpenInference)
# ------------------------------------------------------------
ENABLE_PHOENIX = os.getenv("ENABLE_PHOENIX", "true").lower() == "true"

tracer_provider = None
if ENABLE_PHOENIX:
    try:
        tracer_provider = register(
            project_name=os.getenv("PHOENIX_PROJECT", "agentic-agents"),
            batch=True,
            auto_instrument=True,
        )
        LangChainInstrumentor(tracer_provider=tracer_provider).instrument(skip_dep_check=True)
        try:
            _px_session = px.launch_app()
        except Exception:
            _px_session = None
    except Exception:
        tracer_provider = None

'''
# ------------------------------------------------------------
# Conversation store (Redis-backed, sessionized)
# ------------------------------------------------------------
# Was a plain process-local dict - each FastAPI replica held its own,
# independent ConversationStore with nothing shared between them. A
# session_id routed to two different replicas would silently see two
# different conversation histories. Redis gives any number of replicas
# one shared source of truth.
_SESSION_TTL_SECONDS = 60 * 60 * 24 * 3  # 3 days


class ConversationStore:
    def __init__(self, max_messages: int = 8):
        self._max_messages = max_messages

    def _key(self, session_id: str) -> str:
        return f"conversation:{session_id}"

    async def get_history(self, session_id: str) -> List[BaseMessage]:
        raw = await get_redis().get(self._key(session_id))
        if not raw:
            return []
        return messages_from_dict(json.loads(raw))

    async def append(self, session_id: str, messages: List[BaseMessage]) -> None:
        """Append a batch of messages and enforce the max window."""
        if not messages:
            return
        hist = await self.get_history(session_id)
        hist.extend(messages)
        if len(hist) > self._max_messages:
            hist = hist[-self._max_messages:]
        await get_redis().set(
            self._key(session_id),
            json.dumps(messages_to_dict(hist)),
            ex=_SESSION_TTL_SECONDS,
        )

    async def reset(self, session_id: str) -> None:
        await get_redis().delete(self._key(session_id))

    async def size(self, session_id: str) -> int:
        return len(await self.get_history(session_id))


conversation_store = ConversationStore(max_messages=MAX_SESSION_MESSAGES)


# ------------------------------------------------------------
# Agent service (async, JSON-safe, V1-aligned)
# ------------------------------------------------------------
class AgentService:
    """
    Session-aware facade:
    - Keeps a lightweight per-session history (trimmed).
    - Returns JSON-safe payload: dict/list (preferred) or {"text": "..."} or {"error": "..."}.
    - Includes tracing + detailed logging hooks per turn.
    """

    def __init__(self, store: ConversationStore):
        self.store = store

    def _build_envelope(
        self,
        user_input: Any,
        session_id: str,
        turn_id: str,
        context: Optional[Dict[str, Any]],
    ) -> str:
        """Wrap user input with session/turn context so tools/LLM can pick them up deterministically."""
        return json.dumps(
            {
                "user_input": user_input,
                "context": {
                    **(context or {}),
                    "session_id": session_id,
                    "turn_id": turn_id,
                },
            },
            ensure_ascii=False,
        )

    def _extract_final_content(self, result: Dict[str, Any]) -> Any:
        """
        Converts LangChain messages to JSON-safe final payload.
        - If last message content is JSON, returns parsed dict/list.
        - Else returns {"text": "..."}.
        """
        msgs = result.get("messages") or []
        if not msgs:
            return {"error": "agent_returned_no_messages"}

        last = msgs[-1]
        content = getattr(last, "content", None)
        if content is None:
            return {"error": "agent_returned_no_content"}

        if isinstance(content, (dict, list)):
            return content

        if isinstance(content, str):
            s = content.strip()
            try:
                return json.loads(s)
            except Exception:
                return {"text": s}

        return {"text": str(content)}
    
    def _extract_metadata(self, result: Dict[str, Any]) -> Any:
        """
        Converts LangChain messages to JSON-safe final payload.
        - If last message content is JSON, returns parsed dict/list.
        - Else returns {"text": "..."}.
        """
        msgs = result.get("messages") or []
        if not msgs:
            return {"error": "agent_returned_no_messages"}

        last = msgs[-1]
        metadata = getattr(last, "response_metadata", None)
        if metadata is None:
            return {"error": "agent_returned_no_response_metadata"}
        try:
            return{
                'total_duration': metadata["total_duration"],
                'load_duration':metadata["load_duration"],
                "prompt_eval_duration": metadata["prompt_eval_duration"],
                'eval_duration':metadata["eval_duration"],
                'prompt_eval_count': metadata["prompt_eval_count"],
                'eval_count':metadata["eval_count"]
        }

        except:
            return metadata

    async def achat(
        self,
        session_id: str,
        user_input: Any,
        context: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Async chat entry point (use this in your API)."""
        if user_input is None or (isinstance(user_input, str) and not user_input.strip()):
            return {"error": "invalid_user_input"}

        # Serializes turns for the same session: without this, two
        # overlapping requests for the same session_id (double-click,
        # multiple tabs) could both read the same starting history, run
        # concurrently, and append their results in a nondeterministic
        # order. A Redis lock (not just an in-process one) is needed since
        # /chat and /chat/async can run this in different processes.
        lock = get_redis().lock(f"conversation-lock:{session_id}", timeout=120, blocking_timeout=30)
        acquired = await lock.acquire()
        if not acquired:
            return {"error": "session_busy_try_again"}

        try:
            # 1) New turn + envelope + log
            turn_id = new_turn_id()
            envelope = self._build_envelope(user_input, session_id, turn_id, context)

            # 2) Persist user message (enforced trim via store)
            user_msg = make_human_message(envelope)
            await self.store.append(session_id, [user_msg])

            # 3) Log user turn (DB/analytics)
            try:
                await log_user_message(session_id, turn_id, user_input, context)
            except Exception as e:
                logger.warning("log_user_message failed: %s", e)

            # 4) Run agent on the last CONTEXT_MESSAGES_SENT messages - a
            # separate knob from MAX_SESSION_MESSAGES (which controls how
            # much is *retained*): a single turn already spans several
            # messages (human -> AI tool-call -> tool result -> ... ->
            # final AI), so a small fixed slice here was cutting off the
            # model's own current-turn tool trace, let alone prior turns.
            history = await self.store.get_history(session_id)
            started_at = time.time()
            result = await run_agent_with_history(history[-CONTEXT_MESSAGES_SENT:])
            elapsed = time.time() - started_at

            # 5) Persist agent messages into the session history
            agent_messages = result.get("messages") or []

            await self.store.append(session_id, agent_messages)

            steps = extract_pipeline_main(agent_messages) or []

            # 7) Return a JSON-safe final payload
            final_answer = self._extract_final_content(result)

            metadata = self._extract_metadata(result)

            try:
                await log_assistant_final(session_id, turn_id, {"user_question ": user_input, "final_answer": steps}, str(elapsed))
            except Exception as e:
                logger.warning("log_assistant_final failed: %s", e)

            return {"final_answer": final_answer, "metadata": metadata}
        finally:
            try:
                await lock.release()
            except Exception:
                pass

    async def areset(self, session_id: str) -> None:
        await self.store.reset(session_id)

    async def history_length(self, session_id: str) -> int:
        return await self.store.size(session_id)


agent_service = AgentService(conversation_store)
