# Image for the src/ application (orchestrator and every sub-agent).
#
# One image serves all of them: what a container runs is decided by
# AGENT_ROLE and AGENT_DOMAIN in its environment, not by which directory
# was copied in. That is what allows each deployment to carry its own
# Postgres credentials, and therefore its own least-privilege role.
FROM python:3.11-slim-bookworm

# Runs as a non-root user: a container that never needs to write to its
# own filesystem should not be able to.
RUN groupadd --gid 1000 app \
 && useradd --uid 1000 --gid app --create-home app

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc curl \
 && rm -rf /var/lib/apt/lists/*

COPY src/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=app:app src/ /app/

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://localhost:8000/api/v1/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
