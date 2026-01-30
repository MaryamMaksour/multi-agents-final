
# service.py
from __future__ import annotations

from threading import RLock
from typing import Any, Dict, Optional, List
import json
import os
import logging
import time

from langchain_core.messages import BaseMessage

from openinference.instrumentation.langchain import LangChainInstrumentor
import phoenix as px
from phoenix.otel import register

from .running_agent import run_agent_with_history, make_human_message

from main.config import MAX_SESSION_MESSAGES
from main.history_repo import new_turn_id, log_user_message, log_assistant_final
from main.pipeline_utils import extract_pipeline_main

logger = logging.getLogger(__name__)

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


# ------------------------------------------------------------
# Conversation store (sessionized, thread-safe)
# ------------------------------------------------------------
class ConversationStore:
    def __init__(self, max_messages: int = 8):
        self._histories: Dict[str, List[BaseMessage]] = {}
        self._lock = RLock()
        self._max_messages = max_messages

    def get_history(self, session_id: str) -> List[BaseMessage]:
        with self._lock:
            return self._histories.setdefault(session_id, [])

    def append(self, session_id: str, messages: List[BaseMessage]) -> None:
        """Append a batch of messages and enforce the max window."""
        with self._lock:
            hist = self._histories.setdefault(session_id, [])
            hist.extend(messages)
            if len(hist) > self._max_messages:
                self._histories[session_id] = hist[-self._max_messages :]

    # (Optional convenience) allow single-message append
    def append_one(self, session_id: str, message: BaseMessage) -> None:
        self.append(session_id, [message])

    def reset(self, session_id: str) -> None:
        with self._lock:
            self._histories[session_id] = []

    def size(self, session_id: str) -> int:
        with self._lock:
            return len(self._histories.get(session_id, []))


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

        # 1) New turn + envelope + log
        turn_id = new_turn_id()
        envelope = self._build_envelope(user_input, session_id, turn_id, context)

        # 2) Persist user message (enforced trim via store)
        user_msg = make_human_message(envelope)
        self.store.append(session_id, [user_msg])

        # 3) Log user turn (DB/analytics)
        try:
            await log_user_message(session_id, turn_id, user_input, context)
        except Exception as e:
            logger.warning("log_user_message failed: %s", e)

        # 4) Run agent on the last N messages (keep short context)
        history = self.store.get_history(session_id)
        started_at = time.time()
        result = await run_agent_with_history(history[-5:])
        elapsed = time.time() - started_at

        

        # 5) Persist agent messages into the session history
        agent_messages = result.get("messages") or []

        self.store.append(session_id, agent_messages)

        steps = extract_pipeline_main(agent_messages) or []

        # 7) Return a JSON-safe final payload
        final_answer = self._extract_final_content(result)

        metadata = self._extract_metadata(result)

        try:
            await log_assistant_final(session_id, turn_id, {"user_question ": user_input , "final_answer": steps}, str(elapsed))
        except Exception as e:
            logger.warning("log_assistant_final failed: %s", e)

        return {"final_answer":final_answer,  "metadata": metadata}

    async def areset(self, session_id: str) -> None:
        self.store.reset(session_id)

    def history_length(self, session_id: str) -> int:
        return self.store.size(session_id)


agent_service = AgentService(conversation_store)
