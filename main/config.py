
# main/config.py
import os

# --- Ollama ---
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://192.168.43.220:11435")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:14b")
OLLAMA_TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE", "0.1"))
OLLAMA_NUM_PREDICT = int(os.getenv("OLLAMA_NUM_PREDICT", "32000"))
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "10m")
OLLAMA_MAX_WINDOW_TOKENS = int(os.getenv("OLLAMA_MAX_WINDOW_TOKENS", "32000"))

EMBED_MODEL = os.getenv("EMBED_MODEL", "bge-large")

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

