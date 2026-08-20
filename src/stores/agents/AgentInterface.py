"""The contract the orchestrator sees.

Everything the orchestrator can delegate to implements this, and it
implements nothing else. That is what keeps the orchestrator free of any
knowledge of agent kinds: a SQL agent running in this process and a
spreadsheet agent running behind HTTP are both just an `ainvoke`, and
the orchestrator's tool list is built from `key` and `description`.

Adding a new kind of agent therefore never changes the orchestrator.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class AgentInterface(ABC):

    #: registry key, e.g. "hr"
    key: str
    #: what this agent can answer - becomes the delegation tool's description
    description: str

    @abstractmethod
    async def ainvoke(
        self,
        query: str,
        session_id: str,
        offset: int = 0,
        principal: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Answer one question. Returns a JSON-safe dict."""
        ...

    async def health(self) -> Dict[str, Any]:
        return {"agent": self.key, "status": "ok"}
