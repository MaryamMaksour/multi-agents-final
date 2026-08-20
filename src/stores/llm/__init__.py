from helpers import config as app_config

from .LLMEnums import LLMEnums
from .LLMProviderFactory import LLMProviderFactory

_provider = None


def get_llm_provider():
    """Lazily-built, process-wide QwenProvider singleton."""
    global _provider
    if _provider is None:
        _provider = LLMProviderFactory(app_config).create(LLMEnums.QWEN.value)
    return _provider


def get_chat_model():
    """LangChain chat model, for .bind_tools()/.ainvoke() in the RAG agent loop."""
    return get_llm_provider().get_chat_model()


async def embed_query_async(text: str) -> str:
    """Async embedding, returned as a pgvector-cast-ready literal string."""
    return await get_llm_provider().embed_text_async(text)
