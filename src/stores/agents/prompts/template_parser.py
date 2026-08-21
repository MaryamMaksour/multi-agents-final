"""Loads prompt templates by language, with a fallback.

Same shape as mini_rag's TemplateParser. Prompts live as data under
locales/<lang>/, not as f-strings next to the code that uses them,
which is what lets four domains share one prompt body: the parts that
actually differ per domain are passed in as variables.

Before this, each sub-agent carried its own ~150-line prompt file. They
were roughly 85% identical, so every fix to the shared 85% had to be
made four times - and in practice was not, so they drifted.
"""
from __future__ import annotations

import importlib
import logging
from string import Template
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class TemplateParser:

    def __init__(self, language: str = "en", default_language: str = "en"):
        self.default_language = default_language
        self.language = language or default_language

    def _load(self, language: str, group: str):
        module_path = f"stores.agents.prompts.locales.{language}.{group}"
        try:
            return importlib.import_module(module_path)
        except ModuleNotFoundError:
            return None

    def get(self, group: str, key: str, variables: Optional[Dict[str, Any]] = None) -> str:
        module = self._load(self.language, group)
        if module is None or not hasattr(module, key):
            module = self._load(self.default_language, group)

        if module is None:
            raise ValueError(f"No prompt group {group!r} for language {self.language!r}.")

        template = getattr(module, key, None)
        if template is None:
            raise ValueError(f"No prompt {key!r} in group {group!r}.")

        if not isinstance(template, Template):
            template = Template(str(template))

        # safe_substitute so a prompt containing a literal '$' - a SQL
        # placeholder like $1, which these prompts are full of - never
        # raises. Only the named variables are replaced.
        return template.safe_substitute(variables or {})
