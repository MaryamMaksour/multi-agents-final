"""Application settings.

Every value the app reads from the environment is declared here, with a
type, so a missing or malformed variable fails loudly at startup instead
of surfacing as a confusing runtime error later.

Replaces the scattered `os.getenv` calls in the old `main/config.py`.
"""
from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    # ---------------------------------------------------------------
    # App identity
    # ---------------------------------------------------------------
    APP_NAME: str = "multi-agents"
    APP_VERSION: str = "2.0.0"

    # Which process this is. One image, one codebase - the role and the
    # domain decide what the process serves. This is what lets each
    # deployment carry its own least-privilege Postgres role.
    AGENT_ROLE: str = "orchestrator"          # orchestrator | sub_agent
    AGENT_DOMAIN: Optional[str] = None        # required when AGENT_ROLE=sub_agent

    # ---------------------------------------------------------------
    # LLM backend (OpenAI-compatible)
    # ---------------------------------------------------------------
    # GENERATION_BACKEND selects the provider from LLMProviderFactory.
    # "openai_compat" covers both the hosted URL used today and a local
    # vLLM server later - only LLM_API_URL changes.
    GENERATION_BACKEND: str = "openai_compat"
    EMBEDDING_BACKEND: str = "openai_compat"

    LLM_API_KEY: str = ""
    LLM_API_URL: str
    GENERATION_MODEL_ID: str
    GENERATION_DEFAULT_TEMPERATURE: float = 0.1
    GENERATION_DEFAULT_MAX_TOKENS: int = 32000

    EMBEDDING_MODEL_ID: str
    EMBEDDING_MODEL_SIZE: int = 1024

    # ---------------------------------------------------------------
    # PostgreSQL / pgvector
    # ---------------------------------------------------------------
    # No functional-looking defaults on purpose: an unset value should
    # fail to connect loudly, not quietly reach some other database.
    PG_HOST: str
    PG_PORT: int = 5432
    PG_DBNAME: str
    PG_USER: str
    PG_PASSWORD: str
    PG_SSL: bool = False

    DB_POOL_MIN: int = 1
    DB_POOL_MAX: int = 10
    DB_COMMAND_TIMEOUT: float = 60.0

    # pgvector distance operator: '<->' L2, '<#>' inner product, '<=>' cosine
    DIST_OP: str = "<=>"

    # ---------------------------------------------------------------
    # Redis (orchestrator conversation window)
    # ---------------------------------------------------------------
    REDIS_URL: str = "redis://redis:6379/1"
    SESSION_TTL_SECONDS: int = 60 * 60 * 24 * 3
    MAX_SESSION_MESSAGES: int = 40

    # ---------------------------------------------------------------
    # Tool limits (enforced in code, never left to the prompt)
    # ---------------------------------------------------------------
    SQL_DEFAULT_LIMIT: int = 6
    SQL_MAX_LIMIT: int = 100
    SQL_MAX_OFFSET: int = 5000
    SQL_STATEMENT_TIMEOUT_MS: int = 30000
    AGENT_MAX_ITERATIONS: int = 12

    # ---------------------------------------------------------------
    # Semantic memory (few-shot examples)
    # ---------------------------------------------------------------
    MEMORY_ENABLED: bool = True
    MEMORY_GOOD_EXAMPLES: int = 3
    MEMORY_BAD_EXAMPLES: int = 1
    MEMORY_WINDOW_DAYS: int = 3

    # ---------------------------------------------------------------
    # Sub-agent routing (orchestrator -> sub-agents)
    # ---------------------------------------------------------------
    # "domain=url" pairs, e.g. ["hr=http://agent-hr:8002", "crm=http://agent-crm:8003"].
    # The orchestrator builds one delegation tool per entry, so adding a
    # domain never means editing the orchestrator's code.
    SUB_AGENT_URLS: List[str] = []
    SUB_AGENT_TIMEOUT_SECS: int = 60

    # ---------------------------------------------------------------
    # Authorization seam
    # ---------------------------------------------------------------
    # When enabled, every SQL statement runs inside a transaction that
    # first issues `SET LOCAL app.user_id = <principal>`, so Postgres
    # row-level security policies apply. Off until RLS policies exist.
    RLS_ENABLED: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def sub_agent_routes(self) -> dict:
        routes = {}
        for entry in self.SUB_AGENT_URLS:
            if "=" not in entry:
                raise ValueError(
                    f"SUB_AGENT_URLS entry must look like 'domain=url', got {entry!r}"
                )
            key, url = entry.split("=", 1)
            routes[key.strip().lower()] = url.strip().rstrip("/")
        return routes


def get_settings() -> Settings:
    return Settings()
