from abc import ABC, abstractmethod

# Note: this deliberately isn't shaped like mini_rag's VectorDBInterface
# (connect/create_collection/insert_one/search_by_vector...). This app's
# agents run LLM-authored, parameterized SQL against many relational
# tables - some of which happen to have pgvector columns - not a fixed
# insert/search API against one vector collection. Forcing the
# collection-shaped interface here would misrepresent what db_execute
# actually does (see controllers/tools.py).


class DBInterface(ABC):

    @abstractmethod
    async def connect(self):
        """Creates (if needed) and returns the connection pool."""
        pass

    @abstractmethod
    async def disconnect(self):
        pass

    @abstractmethod
    async def get_pool(self):
        """Returns the underlying connection pool, connecting first if needed."""
        pass
