FROM ghcr.io/astral-sh/uv:0.6.14-python3.11-bookworm

WORKDIR /app

# Install additional system dependencies (asyncpg/psycopg build deps, curl for healthchecks)
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY src/requirements.txt .

RUN uv pip install -r requirements.txt --system

# Flattens src/'s contents (controllers/, routes/, stores/, helpers/,
# utils/, assets/) directly onto /app, same as mini_rag's src/ - so every
# service below imports them unprefixed (`from controllers.factory import
# ...`, `from helpers.static import domain`, etc.).
COPY src/ .

# Each independently deployable service keeps its own top-level directory
# (adding/removing an agent is just adding/removing one of these - no
# changes needed to the shared src/ layer above).
COPY agents-service/ ./agents-service/
COPY agent1-service-property/ ./agent1-service-property/
COPY agent2-service-hr/ ./agent2-service-hr/
COPY agent3-service-crm/ ./agent3-service-crm/
COPY agent4-service-sales-payments/ ./agent4-service-sales-payments/

COPY docker/app/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]

# Default command; overridden per-service by docker-compose.yml
CMD ["uvicorn", "agents-service.main:app", "--host", "0.0.0.0", "--port", "8000"]
