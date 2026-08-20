from __future__ import annotations

import asyncio
import logging
from typing import List, Optional

from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from ..LLMEnums import QwenEnums
from ..LLMInterface import LLMInterface

logger = logging.getLogger(__name__)


def _vector_to_literal(vec: List[float]) -> str:
    return "[" + ", ".join(str(float(x)) for x in vec) + "]"


class QwenProvider(LLMInterface):
    """
    Qwen (DashScope OpenAI-compatible API) provider: handles both chat
    generation and embeddings, same as mini_rag's QwenProvider.
    """

    def __init__(
        self,
        api_key: str,
        api_url: str,
        default_generation_model: Optional[str] = None,
        default_embedding_model: Optional[str] = None,
        default_temperature: float = 0.1,
        default_max_tokens: int = 32000,
    ):
        self.api_key = api_key
        self.api_url = api_url
        self.generation_model_id = default_generation_model
        self.embedding_model_id = default_embedding_model
        self.embedding_size = None
        self.default_temperature = default_temperature
        self.default_max_tokens = default_max_tokens

        self._chat_model: Optional[ChatOpenAI] = None
        self._embedder: Optional[OpenAIEmbeddings] = None

    def set_generation_model(self, model_id: str):
        self.generation_model_id = model_id
        self._chat_model = None

    def set_embedding_model(self, model_id: str, embedding_size: int = None):
        self.embedding_model_id = model_id
        self.embedding_size = embedding_size
        self._embedder = None

    def get_chat_model(self) -> ChatOpenAI:
        if not self.generation_model_id:
            raise ValueError("Generation model for Qwen was not set")
        if self._chat_model is None:
            self._chat_model = ChatOpenAI(
                base_url=self.api_url,
                api_key=self.api_key,
                model=self.generation_model_id,
                temperature=self.default_temperature,
                max_tokens=self.default_max_tokens,
            )
        return self._chat_model

    def generate_text(self, prompt: str, chat_history: list = [],
                       max_output_tokens: int = None,
                       temperature: float = None) -> Optional[str]:
        if not self.generation_model_id:
            raise ValueError("Generation model for Qwen was not set")

        model = ChatOpenAI(
            base_url=self.api_url,
            api_key=self.api_key,
            model=self.generation_model_id,
            temperature=temperature if temperature is not None else self.default_temperature,
            max_tokens=max_output_tokens if max_output_tokens is not None else self.default_max_tokens,
        )

        messages = list(chat_history) + [self.construct_prompt(prompt, QwenEnums.USER.value)]
        response = model.invoke([{"role": m["role"], "content": m["text"]} for m in messages])

        if not response or not getattr(response, "content", None):
            logger.error("Error while generating text with Qwen")
            return None

        return response.content

    def _get_embedder(self) -> OpenAIEmbeddings:
        if not self.embedding_model_id:
            raise ValueError("Embedding model for Qwen was not set")
        if self._embedder is None:
            self._embedder = OpenAIEmbeddings(
                model=self.embedding_model_id, base_url=self.api_url, api_key=self.api_key
            )
        return self._embedder

    def embed_text(self, text: str, document_type: str = None) -> str:
        """
        Returns the embedding as a pgvector literal string
        ("[0.1, 0.2, ...]"), ready for an asyncpg ::vector cast - this app
        stores/queries embeddings straight in Postgres/pgvector columns,
        not a separate vector store, so callers need the cast-ready
        literal rather than a raw list.
        """
        vec = self._get_embedder().embed_query(text)
        return _vector_to_literal(vec)

    async def embed_text_async(self, text: str, document_type: str = None) -> str:
        """Async-safe embedding: runs the sync embed call in a thread."""
        return await asyncio.to_thread(self.embed_text, text, document_type)

    def construct_prompt(self, prompt: str, role: str) -> dict:
        return {"role": role, "text": prompt}
