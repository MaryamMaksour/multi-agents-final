from abc import ABC, abstractmethod


class CacheInterface(ABC):

    @abstractmethod
    def connect(self):
        """Creates (if needed) and returns the cache client."""
        pass

    @abstractmethod
    def disconnect(self):
        pass

    @abstractmethod
    def get_client(self):
        """Returns the underlying cache client, connecting first if needed."""
        pass
