# agent_common/running_agent.py
#
# Byte-for-byte identical across all 6 sub-agent services before this was
# extracted, except for which domain's `run_agent` it wrapped - that is now
# an explicit parameter instead of a hardcoded relative import.
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List
import logging

from langchain_core.messages import HumanMessage, BaseMessage

logger = logging.getLogger(__name__)


async def run_agent_without_history(
    message: List[BaseMessage],
    run_agent: Callable[[List[BaseMessage]], Awaitable[Dict[str, Any]]],
) -> Dict[str, Any]:
    result = await run_agent(message)

    if not isinstance(result, dict):
        raise ValueError("Invalid agent output (expected dict).")
    if "messages" not in result or not result["messages"]:
        raise ValueError("Agent returned empty response.")
    return result


def make_human_message(content: str) -> HumanMessage:
    return HumanMessage(content=content)
