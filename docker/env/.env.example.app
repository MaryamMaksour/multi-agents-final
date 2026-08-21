# Copy to docker/env/.env.app and fill in.
#
# Shared by every service. What each container *is* comes from the
# per-service `environment:` block in docker-compose.yml (AGENT_ROLE,
# AGENT_DOMAIN, PG_USER, PG_PASSWORD), which merges over this file - so
# each agent connects as its own least-privilege role while sharing
# everything below.
#
# See src/.env.example for the full annotated list.

APP_NAME=multi-agents
APP_VERSION=2.0.0

# ==================== LLM (OpenAI-compatible) ====================
# Switching to a local vLLM server is a change to LLM_API_URL only:
#   http://vllm:8000/v1   (LLM_API_KEY may stay empty)
GENERATION_BACKEND=openai_compat
EMBEDDING_BACKEND=openai_compat

LLM_API_KEY=
LLM_API_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
GENERATION_MODEL_ID=qwen3-14b
GENERATION_DEFAULT_TEMPERATURE=0.1
GENERATION_DEFAULT_MAX_TOKENS=32000

# Must match the vector(n) width in least_privilege_roles.sql.
EMBEDDING_MODEL_ID=text-embedding-v3
EMBEDDING_MODEL_SIZE=1024

# ==================== PostgreSQL / pgvector ====================
# PG_USER and PG_PASSWORD are NOT set here - each service gets its own
# in docker-compose.yml. Setting them here would hand every agent the
# same database user and undo the role separation.
PG_HOST=pgvector
PG_PORT=5432
PG_DBNAME=Evolution
PG_SSL=false

DB_POOL_MIN=1
DB_POOL_MAX=10
DB_COMMAND_TIMEOUT=60
DIST_OP=<=>

# ==================== Redis (orchestrator only) ====================
# Password must match REDIS_PASSWORD in docker/.env
REDIS_URL=redis://:changeme@redis:6379/1
SESSION_TTL_SECONDS=259200
MAX_SESSION_MESSAGES=40

# ==================== Tool limits ====================
SQL_DEFAULT_LIMIT=6
SQL_MAX_LIMIT=100
SQL_MAX_OFFSET=5000
SQL_STATEMENT_TIMEOUT_MS=30000
AGENT_MAX_ITERATIONS=12

# ==================== Semantic memory ====================
MEMORY_ENABLED=true
MEMORY_GOOD_EXAMPLES=3
MEMORY_BAD_EXAMPLES=1
MEMORY_WINDOW_DAYS=3

# ==================== Authorization ====================
# Turn on once authentication is in place and RLS policies exist.
RLS_ENABLED=false
