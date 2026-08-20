"""Builds an agent from a registry entry.

The product varies by kind: an AgentKind.SQL spec becomes a
SQLDomainAgent, and a future AgentKind.SHEET spec becomes a
SheetAnalysisAgent - a new branch here and a new provider class, with
nothing else in the system changing.

What does *not* vary by domain is the wiring. hr and crm are the same
kind, so they take the same branch and differ only in the spec passed
in. That is the whole point of keeping domains as data: a third SQL
domain is a spec file, not a code change.
"""
from __future__ import annotations

import logging
from typing import Dict, Optional

from models.enums import AgentKind
from models.HistoryModel import HistoryModel
from models.MemoryModel import MemoryModel

from .AgentInterface import AgentInterface
from .providers import HTTPSubAgent, SQLDomainAgent
from .specs import AGENT_REGISTRY, DomainSpec, get_spec

logger = logging.getLogger(__name__)


class AgentProviderFactory:

    def __init__(self, config, pg_client, llm=None, embed_text=None, template_parser=None):
        self.config = config
        self.pg_client = pg_client
        self.llm = llm
        self.embed_text = embed_text
        self.template_parser = template_parser

    async def create(self, domain: str) -> AgentInterface:
        """Builds the agent for `domain` to run inside this process."""
        spec = get_spec(domain)

        if spec.kind is AgentKind.SQL:
            return await self._create_sql_agent(spec)

        raise NotImplementedError(
            f"No provider for agent kind {spec.kind.value!r} yet. "
            "Add one under stores/agents/providers/ and a branch here."
        )

    async def _create_sql_agent(self, spec: DomainSpec) -> SQLDomainAgent:
        if self.llm is None or self.embed_text is None or self.template_parser is None:
            raise RuntimeError(
                "A local SQL agent needs an llm, an embedder and a template parser."
            )

        history_model = await HistoryModel.create_instance(
            pg_client=self.pg_client, config=self.config, table_name=spec.history_table
        )
        memory_model = await MemoryModel.create_instance(
            pg_client=self.pg_client, config=self.config, table_name=spec.history_table
        )

        return SQLDomainAgent(
            spec=spec,
            config=self.config,
            llm=self.llm,
            embed_text=self.embed_text,
            pg_client=self.pg_client,
            history_model=history_model,
            memory_model=memory_model,
            template_parser=self.template_parser,
        )

    def create_remote(self, domain: str, base_url: str) -> HTTPSubAgent:
        """A client for `domain` running as its own service."""
        spec = get_spec(domain)
        return HTTPSubAgent(
            key=spec.key,
            description=spec.tool_description,
            base_url=base_url,
            timeout=self.config.SUB_AGENT_TIMEOUT_SECS,
        )

    def create_all_remote(self) -> Dict[str, HTTPSubAgent]:
        """One client per domain that has a URL configured.

        Driven by SUB_AGENT_URLS, so the orchestrator's set of
        specialists is configuration - a domain that is registered but
        not deployed is simply absent, not a crash.
        """
        agents: Dict[str, HTTPSubAgent] = {}
        for domain, url in self.config.sub_agent_routes().items():
            if domain not in AGENT_REGISTRY:
                logger.warning(
                    "SUB_AGENT_URLS names %r, which is not a registered domain (%s) - skipping.",
                    domain, sorted(AGENT_REGISTRY),
                )
                continue
            agents[domain] = self.create_remote(domain, url)

        missing = sorted(set(AGENT_REGISTRY) - set(agents))
        if missing:
            logger.warning("No URL configured for registered domains: %s", missing)

        return agents
