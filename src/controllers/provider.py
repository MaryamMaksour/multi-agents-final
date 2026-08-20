# controllers/provider.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class ProviderSpec:
    key: str
    title: str
    description: str
    error_label: str
    domain_label: str
    table_name: str
    allowed_tables: List[str]
    system_prompt: str
