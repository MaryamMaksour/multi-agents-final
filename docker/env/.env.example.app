# Copy this file to docker/env/.env.app and fill in real values.
# This is the single env file shared by all 4 FastAPI services (orchestrator
# + 3 consolidated domain sub-agents), celery-worker, and flower (they all
# run from the same image).

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

# ==================== Tool limits ====================
MAX_PAGES_PER_TOOL=5
MAX_SESSION_MESSAGES=40
DB_POOL_MIN=1
DB_POOL_MAX=10
DB_COMMAND_TIMEOUT=60

# ==================== Sub-agent URLs (used by agents-service/agent_tools.py) ====================
PROPERTY_DEALS_AGENT_URL=http://agent-property-deals:8001/chat
PEOPLE_AGENT_URL=http://agent-people:8002/chat
SALES_PAYMENTS_AGENT_URL=http://agent-sales-payments:8003/chat

TOOLS_HTTP_TIMEOUT_SECS=60
DEFAULT_TOOL_SESSION_ID=agents:subsession

# ==================== Celery Task Queue Config ====================
# Must match docker/env/.env.rabbitmq and docker/env/.env.redis below
CELERY_BROKER_URL=amqp://agents_user:changeme@rabbitmq:5672/agents_vhost
CELERY_RESULT_BACKEND=redis://:changeme@redis:6379/0
CELERY_TASK_SERIALIZER=json
CELERY_TASK_TIME_LIMIT=3600
CELERY_TASK_ACKS_LATE=true
CELERY_WORKER_CONCURRENCY=4
CELERY_FLOWER_PASSWORD=
