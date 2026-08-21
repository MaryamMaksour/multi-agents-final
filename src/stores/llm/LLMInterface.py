"""The contract every LLM backend implements.

Same shape as mini_rag's LLMInterface: the application talks to this,
never to a vendor SDK, so swapping the hosted API for a local vLLM
server is a factory change, not a code change.
"""
from abc import ABC, abstractmethod
from typing import Any, List


class LLMInterface(ABC):

    @abstractmethod
    def set_generation_model(self, model_id: str) -> None:
        ...

    @abstractmethod
    def set_embedding_model(self, model_id: str, embedding_size: int) -> None:
        ...

    @abstractmethod
    def bind_tools(self, tools: List[Any]) -> Any:
        """Return a chat client bound to `tools` for tool-calling."""
        ...

    @abstractmethod
    async def generate_text(self, messages: List[Any]) -> Any:
        ...

    @abstractmethod
    async def embed_text(self, text: str) -> List[float]:
        ...
