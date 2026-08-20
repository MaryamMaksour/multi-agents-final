# Docker Setup for Multi-Agent App

This directory contains the Docker setup for the multi-agent application: the
orchestrator (`agents-service`) and its four domain sub-agents, plus the
full observability stack.

Source lives in `src/` (`controllers/`, `routes/`, `stores/`, `helpers/`,
`utils/`, `assets/` - same layout as mini_rag). Each sub-agent is built
from `controllers/factory.py`'s `create_sub_agent()` out of a small
per-domain `ProviderSpec` (see each `agentN-service-*/provider.py`).
Those service directories stay independently deployable - adding or
removing an agent only touches its own directory, not `src/`.

## Services

- **agents-service**: Orchestrator FastAPI app (port 8000, published to the host)
- **agent-property**: Property inventory - developers, projects, buildings, units (port 8001, internal only)
- **agent-hr**: Internal organization - employees, heads of sales, directors, teams, agents, brokers (port 8002, internal only)
- **agent-crm**: External CRM - customers, customer deals, customer request trackers (port 8003, internal only)
- **agent-sales-payments**: Bookings + payment lifecycle (port 8004, internal only)

Sub-agent ports use `expose:` rather than `ports:` - they're reachable from
other containers on the compose network but not published to the host, so
nothing outside the network can call a sub-agent directly and skip the
orchestrator (and its own domain-scoped tool set).

- **Nginx**: Routes to the orchestrator (agents-service)
- **PostgreSQL (pgvector)**: Self-hosted vector-enabled database
- **Postgres-Exporter**: Exports PostgreSQL metrics for Prometheus
- **Prometheus**: Metrics collection
- **Grafana**: Visualization dashboard for metrics
- **Node-Exporter**: System metrics collection
- **Redis**: App-level session/vector-token state (see `src/stores/cache/`)

## Setup Instructions

### 1. Set up environment files

```bash
cd docker/env
cp .env.example.app .env.app
cp .env.example.postgres .env.postgres
cp .env.example.grafana .env.grafana
cp .env.example.postgres-exporter .env.postgres-exporter
cp .env.example.redis .env.redis
```

Make sure the Postgres/Redis credentials in `.env.app` match the values in
`.env.postgres` and `.env.redis` respectively.

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
docker compose up -d pgvector redis postgres-exporter
# Wait for them to be healthy
sleep 30
# Start the application services
docker compose up --build -d agents-service agent-property agent-hr agent-crm agent-sales-payments nginx prometheus grafana node-exporter
```

To tear everything down (including volumes):

```bash
docker compose down -v --remove-orphans
```

### 3. Access the services

- Orchestrator API: http://localhost:8000 (docs at /docs)
- Nginx (serving the orchestrator): http://localhost
- Sub-agents: internal only (not published to the host) - reach them via `docker compose exec` or from inside the network for debugging
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000

## SQL safety

`db_execute` (the tool each sub-agent uses to run LLM-authored SQL) is
validated with `src/controllers/sql_validation.py` - a real SQL parser
(sqlglot), not regex: single SELECT/WITH/UNION statement only, no
`embed_*`/`embedding` columns anywhere in the query, no tables outside
the calling agent's domain, no filesystem/administrative function calls.

That's still an application-layer check. `docker/postgres/least_privilege_roles.sql`
adds the DB-layer backstop: one Postgres role per domain, `SELECT`-only on
that domain's own tables, so a bug in the app-layer check still can't
reach another domain's data. Run it once against the live database, then
see the wiring notes at the bottom of that file for pointing each
service's `PG_USER`/`PG_PASSWORD` at its own role in `docker-compose.yml`.

## Monitoring

Each FastAPI service exposes Prometheus metrics at `/TjgR_87vhp_bs8KJ`
(intentionally not `/metrics`, to avoid casual public discovery). Prometheus
scrapes all 5 services plus node-exporter and postgres-exporter automatically.

Log into Grafana at http://localhost:3000 (default admin/admin) and add
Prometheus (http://prometheus:9090) as a data source.
