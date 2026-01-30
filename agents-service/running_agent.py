
# running_agent.py
from __future__ import annotations

from typing import List, Dict, Any
import logging

from langchain_core.messages import HumanMessage, BaseMessage
from .RAG_Agent import run_agent 

logger = logging.getLogger(__name__)

async def run_agent_with_history(history: List[BaseMessage]) -> Dict[str, Any]:
    """
    Async wrapper that:
      - keeps only the most recent 8 turns
      - awaits the async V1 agent
      - validates the output
      - returns the full result (including pagination if present)
    Expected result structure:
      {'messages': [BaseMessage, ...], 'pagination': {...} (optional)}
    """
    result = await run_agent(history)

    # Validate structure
    if not isinstance(result, dict):
        raise ValueError("Invalid agent output (expected dict).")

    if "messages" not in result or not result["messages"]:
        raise ValueError("Agent returned empty response.")

    return result

def make_human_message(content: str) -> HumanMessage:
    return HumanMessage(content=content)
 
