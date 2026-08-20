"""What one domain has to declare to become a working agent.

A spec is data, not code. Two SQL domains differ only in the values
below - their table list, their relationships, their enum conventions -
so they are two specs over one implementation, not two implementations.

The distinction that matters: a new *kind* of agent (one that reads
spreadsheets, or calls an external API) is different code and gets a new
provider class under providers/. A new *domain* of an existing kind is a
new spec and nothing else.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from models.enums import AgentKind


@dataclass(frozen=True)
class DomainSpec:
    key: str                       # "hr", "crm" - also the AGENT_DOMAIN value
    kind: AgentKind
    title: str                     # FastAPI app title
    description: str               # FastAPI app description
    tool_description: str          # how the orchestrator sees this agent

    history_table: str             # this domain's own history table
    tables: List[str]              # the only tables its SQL may reference
    table_notes: Dict[str, str] = field(default_factory=dict)

    # Prompt fragments. These are the only parts of the system prompt
    # that differ between SQL domains; the rest is shared.
    relations: str = ""
    normalizations: str = ""
    defaults: str = ""
