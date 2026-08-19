
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
PG_DBNAME = os.getenv("PG_DBNAME", "Evolution")
PG_USER = os.getenv("PG_USER", "ev")
PG_PASSWORD = os.getenv("PG_PASSWORD", "Temp@123")  
PG_HOST = os.getenv("PG_HOST", "192.168.4.51")
PG_PORT = int(os.getenv("PG_PORT", "5432"))

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
DB_POOL_MIN = int(os.getenv("DB_POOL_MIN", "1"))
DB_POOL_MAX = int(os.getenv("DB_POOL_MAX", "10"))
DB_COMMAND_TIMEOUT = float(os.getenv("DB_COMMAND_TIMEOUT", "60"))

