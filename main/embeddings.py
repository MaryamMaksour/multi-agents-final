
# main/embeddings.py
import asyncio
from typing import List
from langchain_openai import OpenAIEmbeddings
from main.config import QWEN_API_KEY, QWEN_API_URL, QWEN_EMBED_MODEL

# A single shared embedder (sync implementation underneath)
embedder = OpenAIEmbeddings(model=QWEN_EMBED_MODEL, base_url=QWEN_API_URL, api_key=QWEN_API_KEY)

def vector_to_literal(vec: List[float]) -> str:
    return "[" + ", ".join(str(float(x)) for x in vec) + "]"

def embed_query(text: str):
    """Sync embedding (kept for backward compatibility)."""
    return vector_to_literal(embedder.embed_query(text))


async def embed_query_async(text: str):
    """Async-safe embedding: runs sync embed_query in a thread."""
    return await asyncio.to_thread(embed_query, text)
