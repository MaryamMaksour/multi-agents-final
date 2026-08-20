from .LLMEnums import LLMEnums
from .providers import QwenProvider


class LLMProviderFactory:

    def __init__(self, config):
        self.config = config

    def create(self, provider: str):
        if provider == LLMEnums.QWEN.value:
            return QwenProvider(
                api_key=self.config.QWEN_API_KEY,
                api_url=self.config.QWEN_API_URL,
                default_generation_model=self.config.QWEN_MODEL,
                default_embedding_model=self.config.QWEN_EMBED_MODEL,
                default_temperature=self.config.QWEN_TEMPERATURE,
                default_max_tokens=self.config.QWEN_MAX_TOKENS,
            )

        return None
