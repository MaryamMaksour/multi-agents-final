"""One provider for every OpenAI-compatible endpoint.

The hosted API in use today and a self-hosted vLLM server later speak
the same protocol, so they are the same provider with a different
`base_url` - moving off the hosted API is an .env change, not a code
change. (vLLM also unlocks guided decoding for structurally valid tool
calls; that is a per-request option added here when the switch happens.)
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, List

from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from ..LLMInterface import LLMInterface

logger = logging.getLogger(__name__)


class OpenAICompatProvider(LLMInterface):

    def __init__(
        self,
        api_url: str,
        api_key: str = "",
        default_temperature: float = 0.1,
        default_max_tokens: int = 32000,
    ):
        self.api_url = api_url
        # vLLM served locally usually needs no key; the client still
        # requires a non-empty string, so send a placeholder.
        self.api_key = api_key or "not-needed"
        self.default_temperature = default_temperature
        self.default_max_tokens = default_max_tokens

        self.generation_model_id: str | None = None
        self.embedding_model_id: str | None = None
        self.embedding_size: int | None = None

        self._chat: ChatOpenAI | None = None
        self._embedder: OpenAIEmbeddings | None = None

    # -- configuration ------------------------------------------------
    def set_generation_model(self, model_id: str) -> None:
        self.generation_model_id = model_id
        self._chat = ChatOpenAI(
            base_url=self.api_url,
            api_key=self.api_key,
            model=model_id,
            temperature=self.default_temperature,
            max_tokens=self.default_max_tokens,
        )

    def set_embedding_model(self, model_id: str, embedding_size: int) -> None:
        self.embedding_model_id = model_id
        self.embedding_size = embedding_size
        self._embedder = OpenAIEmbeddings(
            base_url=self.api_url,
            api_key=self.api_key,
            model=model_id,
        )

    # -- use ----------------------------------------------------------
    def bind_tools(self, tools: List[Any]) -> Any:
        if self._chat is None:
            raise RuntimeError("Generation model not set - call set_generation_model first.")
        return self._chat.bind_tools(tools)

    async def generate_text(self, messages: List[Any]) -> Any:
        if self._chat is None:
            raise RuntimeError("Generation model not set - call set_generation_model first.")
        return await self._chat.ainvoke(messages)

    async def embed_text(self, text: str) -> List[float]:
        if self._embedder is None:
            raise RuntimeError("Embedding model not set - call set_embedding_model first.")
        # The client's embed_query is synchronous; keep the event loop free.
        return await asyncio.to_thread(self._embedder.embed_query, text)
