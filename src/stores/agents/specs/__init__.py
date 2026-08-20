"""The agent registry.

Every agent the system knows about is one entry here. This is the single
place that changes when a domain is added: the orchestrator builds its
delegation tools from this registry, and a sub-agent process selects its
own spec from it by AGENT_DOMAIN - so neither has a hardcoded list of
domains anywhere.
"""
from typing import Dict, List

from .DomainSpec import DomainSpec
from . import crm, hr

AGENT_REGISTRY: Dict[str, DomainSpec] = {
    hr.spec.key: hr.spec,
    crm.spec.key: crm.spec,
}


def get_spec(domain: str) -> DomainSpec:
    key = (domain or "").strip().lower()
    if key not in AGENT_REGISTRY:
        raise ValueError(
            f"Unknown domain {domain!r}. Registered domains: {sorted(AGENT_REGISTRY)}"
        )
    return AGENT_REGISTRY[key]


def registered_domains() -> List[str]:
    return sorted(AGENT_REGISTRY)


__all__ = ["DomainSpec", "AGENT_REGISTRY", "get_spec", "registered_domains"]
