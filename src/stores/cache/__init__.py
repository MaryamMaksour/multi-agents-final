from helpers import config as app_config

from .CacheEnums import CacheEnums
from .CacheProviderFactory import CacheProviderFactory

_provider = None


def get_cache_provider():
    """Lazily-built, process-wide RedisProvider singleton."""
    global _provider
    if _provider is None:
        _provider = CacheProviderFactory(app_config).create(CacheEnums.REDIS.value)
    return _provider


def get_redis():
    return get_cache_provider().get_client()
