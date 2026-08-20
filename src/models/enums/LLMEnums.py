from enum import Enum


class LLMEnums(str, Enum):
    """Provider keys accepted by LLMProviderFactory.create()."""
    OPENAI_COMPAT = "openai_compat"


class LLMRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
