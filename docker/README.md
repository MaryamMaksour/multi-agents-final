# Docker Setup for Multi-Agent App

This directory contains the Docker setup for the multi-agent application: the
orchestrator (`agents-service`) and its six sub-agents, plus the Celery task
queue, Flower monitoring, and the full observability stack.

## Services

- **agents-service**: Orchestrator FastAPI app (port 8000)
- **agent-property / agent-hr / agent-crm / agent-deals / agent-sales / agent-payment**:
  Sub-agent FastAPI services (ports 8001-8004, 8006, 8007)
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
docker compose up --build -d agents-service agent-property agent-hr agent-crm agent-deals agent-sales agent-payment celery-worker flower nginx prometheus grafana node-exporter
```

To tear everything down (including volumes):

```bash
docker compose down -v --remove-orphans
```

### 3. Access the services

- Orchestrator API: http://localhost:8000 (docs at /docs)
- Nginx (serving the orchestrator): http://localhost
- Sub-agents: http://localhost:8001 .. 8004, 8006, 8007
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
scrapes all 7 services plus node-exporter and postgres-exporter automatically.

Log into Grafana at http://localhost:3000 (default admin/admin) and add
Prometheus (http://prometheus:9090) as a data source.
