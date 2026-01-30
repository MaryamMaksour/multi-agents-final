
# main/embeddings.py
import asyncio
from typing import List
from langchain_ollama import OllamaEmbeddings
from main.config import OLLAMA_BASE_URL, EMBED_MODEL

# A single shared embedder (sync implementation underneath)
embedder = OllamaEmbeddings(model=EMBED_MODEL, base_url=OLLAMA_BASE_URL)

def vector_to_literal(vec: List[float]) -> str:
    return "[" + ", ".join(str(float(x)) for x in vec) + "]"

def embed_query(text: str):
    """Sync embedding (kept for backward compatibility)."""
    return vector_to_literal(embedder.embed_query(text))


async def embed_query_async(text: str):
    """Async-safe embedding: runs sync embed_query in a thread."""
    return await asyncio.to_thread(embed_query, text)
