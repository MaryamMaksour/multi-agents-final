from helpers import config as app_config

from .DBEnums import DBEnums
from .DBProviderFactory import DBProviderFactory

_provider = None


def get_db_provider():
    """Lazily-built, process-wide PGVectorProvider singleton."""
    global _provider
    if _provider is None:
        _provider = DBProviderFactory(app_config).create(DBEnums.PGVECTOR.value)
    return _provider


async def get_pool():
    return await get_db_provider().get_pool()


async def close_pool() -> None:
    provider = get_db_provider()
    await provider.disconnect()
