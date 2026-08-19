
# main/llm.py
from __future__ import annotations

from langchain_openai import ChatOpenAI
from main.config import (
    QWEN_API_KEY, QWEN_API_URL, QWEN_MODEL, QWEN_TEMPERATURE, QWEN_MAX_TOKENS
)

def get_llm():
    return ChatOpenAI(
        base_url=QWEN_API_URL,
        api_key=QWEN_API_KEY,
        model=QWEN_MODEL,
        temperature=QWEN_TEMPERATURE,
        max_tokens=QWEN_MAX_TOKENS,
    )
