
# running_agent.py
from __future__ import annotations

from typing import List, Dict, Any
import logging

from langchain_core.messages import HumanMessage, BaseMessage
from .RAG_Agent import run_agent

logger = logging.getLogger(__name__)

async def run_agent_without_history(message: List[BaseMessage]) -> Dict[str, Any]:
    
    result = await run_agent(message)
    #print("from running_agent the result of run agent ",result)

    if not isinstance(result, dict):
        raise ValueError("Invalid agent output (expected dict).")
    if "messages" not in result or not result["messages"]:
        raise ValueError("Agent returned empty response.")
    return result

def make_human_message(content: str) -> HumanMessage:
    return HumanMessage(content=content)



