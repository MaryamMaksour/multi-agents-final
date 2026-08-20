"""Selects an LLM backend from configuration.

Same pattern as mini_rag's LLMProviderFactory: `create()` maps a
provider key from the environment onto a concrete LLMInterface. Adding
a backend (a native vLLM client, a different vendor) means one provider
class and one branch here - nothing that uses the LLM changes.
"""
from __future__ import annotations

from models.enums import LLMEnums

from .LLMInterface import LLMInterface
from .providers import OpenAICompatProvider


class LLMProviderFactory:

    def __init__(self, config):
        self.config = config

    def create(self, provider: str) -> LLMInterface:
        if provider == LLMEnums.OPENAI_COMPAT.value:
            return OpenAICompatProvider(
                api_url=self.config.LLM_API_URL,
                api_key=self.config.LLM_API_KEY,
                default_temperature=self.config.GENERATION_DEFAULT_TEMPERATURE,
                default_max_tokens=self.config.GENERATION_DEFAULT_MAX_TOKENS,
            )

        raise ValueError(
            f"Unknown LLM provider {provider!r}. "
            f"Known providers: {[e.value for e in LLMEnums]}"
        )
