
# main/llm.py
from __future__ import annotations

from langchain_ollama import ChatOllama
from main.config import (
    OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_TEMPERATURE,
    OLLAMA_NUM_PREDICT, OLLAMA_KEEP_ALIVE
)

def get_llm():
    # ChatOllama supports these params; some go into "options"
    return ChatOllama(
        base_url=OLLAMA_BASE_URL,
        model=OLLAMA_MODEL,
        temperature=OLLAMA_TEMPERATURE,
        keep_alive=OLLAMA_KEEP_ALIVE,
        # Ollama generation options:
        options={
            "num_predict": OLLAMA_NUM_PREDICT,
        },
    )
