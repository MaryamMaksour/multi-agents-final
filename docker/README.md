# Docker

Runs the `src/` application: one orchestrator and one process per
domain agent, on Postgres/pgvector and Redis, behind nginx.

## Services

| service | port | |
|---|---|---|
| `nginx` | **80** (host) | the only thing published |
| `orchestrator` | 8000 (internal) | talks to the user, delegates |
| `agent-hr` | 8002 (internal) | employees, directors, teams, agents |
| `agent-crm` | 8003 (internal) | customers, their deals and requests |
| `pgvector` | 5432 (internal) | |
| `redis` | 6379 (internal) | orchestrator conversation window |
| `prometheus` | 9090 (**loopback**) | |
| `grafana` | 3000 (**loopback**) | |

All three application containers are the same image. `AGENT_ROLE` and
`AGENT_DOMAIN` in each service's `environment:` block decide what it
serves, so adding an agent is a compose service plus a `SUB_AGENT_URLS`
entry — not a new directory or a new image.

## Running it

```bash
cp docker/.env.example            docker/.env              # passwords
cp docker/env/.env.example.app    docker/env/.env.app
cp docker/env/.env.example.postgres docker/env/.env.postgres
cp docker/env/.env.example.grafana  docker/env/.env.grafana

docker compose -f docker/docker-compose.yml up --build
curl localhost/api/v1/health
```

Nothing has a default password. A missing value in `docker/.env` stops
the stack, which is the intended behaviour.

## Database roles

`postgres/least_privilege_roles.sql` is mounted into the pgvector
container's `docker-entrypoint-initdb.d`, so it runs once when the data
volume is first created. On an existing database, run it by hand as a
superuser.

It creates one role per agent:

- `app_hr` — SELECT on the five organization tables, and its own history
- `app_crm` — SELECT on the three customer tables, and its own history
- `app_orchestrator` — its own history only; it reaches data by
  delegating, never by querying

This is what makes the application-layer SQL validation survivable.
`src/stores/agents/tools/sql_validation.py` parses every query and
rejects tables outside the agent's domain, but it is still application
code. A role that physically cannot see another domain's tables turns a
bug there into an error message.

Two grants are deliberately absent:

- **No `CREATE`.** The history tables are created by this script, so an
  agent can write its own history and nothing else.
- **No `DELETE`.** An agent that can delete its own history has no audit
  trail. Retention runs separately, under a different role.

Change the passwords in this file *and* in `docker/.env` together — the
values must agree.

## Network exposure

Only nginx is published. Postgres, Redis and both application tiers use
`expose:`, which is reachable inside the compose network and nowhere
else; Prometheus and Grafana are bound to `127.0.0.1`, so they are
reachable from the host that runs the stack but not from the network.

Before this stack faces anything real:

- **Terminate TLS at nginx** (it listens on plain 80 today) and set
  `PG_SSL=true`.
- **Authenticate.** `/api/v1/chat` is open. nginx clears `X-Principal`
  from incoming requests, so a client cannot claim an identity, but
  nothing sets a verified one yet.
- **Put Grafana behind an authenticating proxy** if it needs to be
  reachable beyond the host.

## Containers

Non-root, read-only root filesystem, all capabilities dropped,
`no-new-privileges`. Pin image digests before deploying anywhere that
matters.
