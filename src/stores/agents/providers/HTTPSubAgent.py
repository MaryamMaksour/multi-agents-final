"""A sub-agent reached over HTTP.

The orchestrator holds one of these per registered domain. It is a
second implementation of AgentInterface, which is what makes the
transport a choice rather than an assumption: running the same domain
agent in-process instead means constructing SQLDomainAgent here and
changing nothing else, because the orchestrator only ever sees
`ainvoke`.

Running them as separate processes is what allows each to connect as its
own least-privilege Postgres role, which is the real reason to keep the
HTTP hop.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

from ..AgentInterface import AgentInterface

logger = logging.getLogger(__name__)


class HTTPSubAgent(AgentInterface):

    def __init__(self, key: str, description: str, base_url: str, timeout: int = 60):
        self.key = key
        self.description = description
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def ainvoke(
        self,
        query: str,
        session_id: str,
        offset: int = 0,
        principal: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = {
            "session_id": session_id,
            "user_input": query,
            "context": {"offset": offset},
        }

        headers = {"Content-Type": "application/json"}
        if principal:
            # Carried so the sub-agent can pin it onto its database
            # session for row-level security. Signed rather than plain
            # once authentication lands - a sub-agent must be able to
            # tell a real identity from one a caller made up.
            headers["X-Principal"] = principal

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/chat", json=payload, headers=headers
                )
                response.raise_for_status()
                body = response.json()
        except httpx.TimeoutException:
            return {"error": f"{self.key}_agent_timeout after {self.timeout}s"}
        except Exception as error:
            logger.exception("Call to sub-agent %s failed", self.key)
            return {"error": f"{self.key}_agent_unreachable: {error}"}

        return body.get("answer", body)

    async def health(self) -> Dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.base_url}/api/v1/health")
                response.raise_for_status()
            return {"agent": self.key, "status": "ok"}
        except Exception as error:
            return {"agent": self.key, "status": "unreachable", "detail": str(error)}
