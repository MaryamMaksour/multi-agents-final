FROM ghcr.io/astral-sh/uv:0.6.14-python3.11-bookworm

WORKDIR /app

# Install additional system dependencies (asyncpg/psycopg build deps, curl for healthchecks)
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN uv pip install -r requirements.txt --system

COPY . .

COPY docker/app/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]

# Default command; overridden per-service by docker-compose.yml
CMD ["uvicorn", "agents-service.main:app", "--host", "0.0.0.0", "--port", "8000"]
