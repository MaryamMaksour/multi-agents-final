# Docker Setup for Multi-Agent App

This directory contains the Docker setup for the multi-agent application: the
orchestrator (`agents-service`) and its three domain sub-agents, plus the
Celery task queue, Flower monitoring, and the full observability stack.

## Services

- **agents-service**: Orchestrator FastAPI app (port 8000, published to the host)
- **agent-property-deals**: Property inventory + deals (port 8001, internal only)
- **agent-people**: Organization (HR) + CRM (port 8002, internal only)
- **agent-sales-payments**: Bookings + payment lifecycle (port 8003, internal only)

Sub-agent ports use `expose:` rather than `ports:` - they're reachable from
other containers on the compose network but not published to the host, so
nothing outside the network can call a sub-agent directly and skip the
orchestrator (and its own domain-scoped tool set).

- **celery-worker**: Runs `/chat/async` requests from any service as background tasks
- **flower**: Celery task monitoring dashboard (port 5555)
- **Nginx**: Routes to the orchestrator (agents-service)
- **PostgreSQL (pgvector)**: Self-hosted vector-enabled database
- **Postgres-Exporter**: Exports PostgreSQL metrics for Prometheus
- **Prometheus**: Metrics collection
- **Grafana**: Visualization dashboard for metrics
- **Node-Exporter**: System metrics collection
- **RabbitMQ**: Celery broker
- **Redis**: Celery result backend

## Setup Instructions

### 1. Set up environment files

```bash
cd docker/env
cp .env.example.app .env.app
cp .env.example.postgres .env.postgres
cp .env.example.grafana .env.grafana
cp .env.example.postgres-exporter .env.postgres-exporter
cp .env.example.rabbitmq .env.rabbitmq
cp .env.example.redis .env.redis
```

Make sure the Postgres/RabbitMQ/Redis credentials in `.env.app` match the
values in `.env.postgres`, `.env.rabbitmq`, and `.env.redis` respectively.

### 2. Start the services

```bash
cd docker
docker compose up --build -d
```

To start only specific services:

```bash
docker compose up -d agents-service nginx pgvector
```

If you encounter connection issues, start the infra services first and let
them initialize before starting the application:

```bash
# Start infra first
docker compose up -d pgvector rabbitmq redis postgres-exporter
# Wait for them to be healthy
sleep 30
# Start the application services
docker compose up --build -d agents-service agent-property-deals agent-people agent-sales-payments celery-worker flower nginx prometheus grafana node-exporter
```

To tear everything down (including volumes):

```bash
docker compose down -v --remove-orphans
```

### 3. Access the services

- Orchestrator API: http://localhost:8000 (docs at /docs)
- Nginx (serving the orchestrator): http://localhost
- Sub-agents: internal only (not published to the host) - reach them via `docker compose exec` or from inside the network for debugging
- Flower: http://localhost:5555
- RabbitMQ management UI: http://localhost:15672
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000

## Async chat via Celery

Every service exposes the original synchronous endpoints (`/chat`,
`/chat/stream`, `/reset`, `/health`) unchanged, plus two additive endpoints
for queued execution:

- `POST /chat/async` -> `{"task_id": "...", "status": "queued"}`
- `GET /chat/status/{task_id}` -> current Celery task state/result

Track progress for any task in Flower at http://localhost:5555.

## Monitoring

Each FastAPI service exposes Prometheus metrics at `/TjgR_87vhp_bs8KJ`
(intentionally not `/metrics`, to avoid casual public discovery). Prometheus
scrapes all 4 services plus node-exporter and postgres-exporter automatically.

Log into Grafana at http://localhost:3000 (default admin/admin) and add
Prometheus (http://prometheus:9090) as a data source.
