# agent_common/config.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from .service import AgentService


@dataclass
class AgentConfig:
    title: str
    description: str
    error_label: str
    agent_service: AgentService
    ensure_history_schema: Callable[[], Awaitable[None]]
