# agent_common/provider.py
#
# A ProviderSpec is the one thing a domain has to supply to get a fully
# working sub-agent service: its table allowlist, its system prompt, and a
# handful of labels. Everything else - the LangGraph tool-calling loop, the
# history/memory logging, the FastAPI routes - is generic and lives in
# agent_common.factory.create_sub_agent(), which takes a ProviderSpec and
# returns a wired-up AgentConfig. Adding a new domain (a new "provider")
# means writing a ProviderSpec and a prompt.py - nothing about the factory
# itself changes.
from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class ProviderSpec:
    key: str                 # short domain key, e.g. "hr", "crm", "property"
    title: str                # FastAPI app title
    description: str          # FastAPI app description
    error_label: str          # used in the /chat error message text
    domain_label: str         # used in tool-call-failure logging (see rag_agent.py)
    table_name: str           # this provider's history table name
    allowed_tables: List[str]  # the only tables db_execute may reference
    system_prompt: str
