from .DBEnums import DBEnums
from .providers import PGVectorProvider


class DBProviderFactory:

    def __init__(self, config):
        self.config = config

    def create(self, provider: str):
        if provider == DBEnums.PGVECTOR.value:
            return PGVectorProvider(
                host=self.config.PG_HOST,
                port=self.config.PG_PORT,
                dbname=self.config.PG_DBNAME,
                user=self.config.PG_USER,
                password=self.config.PG_PASSWORD,
                ssl=self.config.PG_SSL,
                pool_min=self.config.DB_POOL_MIN,
                pool_max=self.config.DB_POOL_MAX,
            )

        return None
