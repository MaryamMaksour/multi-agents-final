# Copy this file to docker/env/.env.app and fill in real values.
# This is the single env file shared by all 5 FastAPI services (orchestrator
# + 4 domain sub-agents: property, hr, crm, sales+payments - they all run
# from the same image).

# ==================== Qwen (DashScope OpenAI-compatible API) Config ====================
QWEN_API_KEY=
QWEN_API_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen3-14b
QWEN_TEMPERATURE=0.1
QWEN_MAX_TOKENS=32000

QWEN_EMBED_MODEL=text-embedding-v3

# ==================== PostgreSQL / pgvector Config ====================
# Must match docker/env/.env.postgres (POSTGRES_USER/PASSWORD/DB below)
PG_DBNAME=Evolution
PG_USER=ev
PG_PASSWORD=
PG_HOST=pgvector
PG_PORT=5432
PG_SSL=false

DIST_OP=<=>

# ==================== Redis (app-level session/vector-token state) ====================
# Must match docker/env/.env.redis's REDIS_PASSWORD
REDIS_URL=redis://:changeme@redis:6379/1

# ==================== Tool limits ====================
MAX_PAGES_PER_TOOL=5
MAX_SESSION_MESSAGES=40
CONTEXT_MESSAGES_SENT=20
DB_POOL_MIN=1
DB_POOL_MAX=10
DB_COMMAND_TIMEOUT=60

# ==================== Sub-agent URLs (used by agents-service/agent_tools.py) ====================
PROPERTY_AGENT_URL=http://agent-property:8001/chat
HR_AGENT_URL=http://agent-hr:8002/chat
CRM_AGENT_URL=http://agent-crm:8003/chat
SALES_PAYMENTS_AGENT_URL=http://agent-sales-payments:8004/chat

TOOLS_HTTP_TIMEOUT_SECS=60
DEFAULT_TOOL_SESSION_ID=agents:subsession
