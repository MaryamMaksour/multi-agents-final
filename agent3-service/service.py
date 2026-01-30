
# service.py
from __future__ import annotations
import logging

import time
import json

from typing import Any, Dict, Optional

from .running_agent import run_agent_without_history, make_human_message 
from .history_repo_1 import  new_turn_id, log_user_message, log_assistant_final 
from main.pipeline_utils import extract_pipeline


logger = logging.getLogger(__name__)

# ============================================================
# Stateless Agent Service
# ============================================================

class AgentService:
    """
    Session-aware sub-agent facade:
    - Returns JSON-safe object (dict/list) or {"text": "..."} or {"error": "..."}.
    """
    
    def _build_envelope(self, user_input: Any, session_id, turn_id, cursor = '') -> str:
        return json.dumps(
            {"user_input": user_input, "context": {
                                            "cursor": cursor,
                                            "session_id": session_id,
                                            "turn_id": turn_id
                                        }
            },ensure_ascii=False
        )


    def _extract_final_content(self, result: Dict[str, Any], steps: list) -> Any:
        """
        Extract final LLM content and enrich with SQL + params
        from the last db_execute tool call inside steps.
        """

        msgs = list(result.get("messages") or [])

        # 1) Parse final message
        if not msgs:
            final_payload = {"error": "agent_returned_no_messages"}
        else:
            last = msgs[-1]
            content = getattr(last, "content", None)
            if content is None:
                final_payload = {"error": "agent_returned_no_content"}
            elif isinstance(content, (dict, list)):
                final_payload = content
            elif isinstance(content, str):
                s = content.strip()
                try:
                    final_payload = json.loads(s)
                except Exception:
                    final_payload = {"text": s}
            else:
                final_payload = {"text": str(content)}

        # 2) Extract last SQL+params (guard steps)
        last_sql_args = None
        for step in (steps or []):
            if not isinstance(step, dict):
                continue
            if step.get("type") == "tool" and step.get("name") == "db_execute":
                args = step.get("args") or {}
                last_sql_args = {
                    "sql": args.get("query"),
                    "params": args.get("params"),
                }

        # 3) Merge params into final payload if missing
        if isinstance(final_payload, dict) and last_sql_args:
            if final_payload.get("params") is None:
                final_payload["params"] = last_sql_args["params"]

        return final_payload

    

    async def achat(self, session_id: str, user_input: Any,  context: Optional[Dict[str, Any]] = None) -> Any:
        
        if user_input is None or (isinstance(user_input, str) and not user_input.strip()):
            return {"error": "invalid_user_input"}
        
        turn_id = new_turn_id()
       
        cursor = (context or {}).get('cursor', None)
        envelope = self._build_envelope(user_input, session_id, turn_id, cursor)
        
        
        try:
            await log_user_message(session_id, turn_id, user_input, context)
        except:
            pass


        start_time = time.time()
        result = await run_agent_without_history([make_human_message(envelope)])
        end_time = time.time()
        
        # Guard if the agent returned None
        if result is None:
            # Option A: return 200 with a structured error for the client to show gracefully
            return {"error": "agent_returned_none"}

        # Store agent messages too (so multi-turn works)
        agent_messages = result.get("messages") or []
        steps = extract_pipeline(agent_messages) or []

        final_payload = self._extract_final_content(result, steps)  


        try:
            await log_assistant_final(session_id, turn_id, steps, str( end_time - start_time))
        except:
            pass

        return final_payload
    

    async def areset(self, session_id: str) -> None:
        return None

    def history_length(self, session_id: str) -> int:
        return 1

agent_service = AgentService()
