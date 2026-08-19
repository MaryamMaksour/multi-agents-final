# Copy this file to docker/env/.env.app and fill in real values.
# This is the single env file shared by all 7 FastAPI services, celery-worker,
# and flower (they all run from the same image).

# ==================== Ollama / LLM Config ====================
OLLAMA_BASE_URL=http://192.168.43.220:11435
OLLAMA_MODEL=qwen3:14b
OLLAMA_TEMPERATURE=0.1
OLLAMA_NUM_PREDICT=32000
OLLAMA_KEEP_ALIVE=10m
OLLAMA_MAX_WINDOW_TOKENS=32000

EMBED_MODEL=bge-large

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
PROPERTY_AGENT_URL=http://agent-property:8001/chat
ORGANIZATION_AGENT_URL=http://agent-hr:8002/chat
CRM_AGENT_URL=http://agent-crm:8003/chat
DEALS_AGENT_URL=http://agent-deals:8004/chat
SALES_AGENT_URL=http://agent-sales:8006/chat
PAYMENT_AGENT_URL=http://agent-payment:8007/chat

TOOLS_HTTP_TIMEOUT_SECS=3600
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
