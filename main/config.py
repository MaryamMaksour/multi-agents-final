
# main/config.py
import os

# --- Qwen (DashScope OpenAI-compatible API) ---
QWEN_API_KEY = os.getenv("QWEN_API_KEY", "")
QWEN_API_URL = os.getenv("QWEN_API_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1")
QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen3-14b")
QWEN_TEMPERATURE = float(os.getenv("QWEN_TEMPERATURE", "0.1"))
QWEN_MAX_TOKENS = int(os.getenv("QWEN_MAX_TOKENS", "32000"))

QWEN_EMBED_MODEL = os.getenv("QWEN_EMBED_MODEL", "text-embedding-v3")

# --- PostgreSQL / pgvector ---
# No functional-looking fallback values here on purpose: a missing
# PG_PASSWORD/PG_HOST used to silently default to a real password and a
# real internal IP baked into source control. An unset value should fail
# to connect loudly, not quietly reach some other network's database.
PG_DBNAME = os.getenv("PG_DBNAME", "")
PG_USER = os.getenv("PG_USER", "")
PG_PASSWORD = os.getenv("PG_PASSWORD", "")
PG_HOST = os.getenv("PG_HOST", "")
PG_PORT = int(os.getenv("PG_PORT", "5432"))

# --- Redis (app-level session/vector state) ---
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/1")

# Optional TLS
PG_SSL = os.getenv("PG_SSL", "false").lower() == "true"

# --- Retrieval distance operator ---
# pgvector supports '<->'(L2), '<#>'(inner product), '<=>'(cosine)
DIST_OP = os.getenv("DIST_OP", "<=>")

# ----- Tools -----
property_TOOL = os.getenv("property_TOOL", "property")
Organization_TOOL = os.getenv("Organization_TOOL", "organization")
DEALS_TOOL = os.getenv("DEALS_TOOL", "deals")

# --- Tool limits ---
MAX_PAGES_PER_TOOL = int(os.getenv("MAX_PAGES_PER_TOOL", "5"))
MAX_SESSION_MESSAGES = int(os.getenv("MAX_SESSION_MESSAGES", "40"))
# How many of the retained session messages actually get sent to the LLM
# per turn. Separate from MAX_SESSION_MESSAGES on purpose - that one
# controls how much history is kept; this one controls how much of it is
# used as context. A single turn already spans several messages (human ->
# AI tool-call -> tool result -> ... -> final AI), so this needs to be a
# multiple of that, not a small fixed slice.
CONTEXT_MESSAGES_SENT = int(os.getenv("CONTEXT_MESSAGES_SENT", "20"))
DB_POOL_MIN = int(os.getenv("DB_POOL_MIN", "1"))
DB_POOL_MAX = int(os.getenv("DB_POOL_MAX", "10"))
DB_COMMAND_TIMEOUT = float(os.getenv("DB_COMMAND_TIMEOUT", "60"))

