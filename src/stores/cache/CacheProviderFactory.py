from .CacheEnums import CacheEnums
from .providers import RedisProvider


class CacheProviderFactory:

    def __init__(self, config):
        self.config = config

    def create(self, provider: str):
        if provider == CacheEnums.REDIS.value:
            return RedisProvider(url=self.config.REDIS_URL)

        return None
