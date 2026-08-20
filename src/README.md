# `src/` — multi-agent SQL question answering

A main agent talks to the user and delegates each question to the
specialist that owns that data. Specialists answer by writing SQL
against their own tables, and only their own tables.

Laid out the way the RAG-mini reference does it: everything the
application is lives under `src/`, split into `models/` (data),
`controllers/` (logic), `routes/` (HTTP only), and `stores/`
(swappable backends behind interfaces).

---

## Running it

One image serves every process. Two environment variables decide what a
process is:

```bash
AGENT_ROLE=orchestrator                  uvicorn main:app --port 8000
AGENT_ROLE=sub_agent AGENT_DOMAIN=hr     uvicorn main:app --port 8002
AGENT_ROLE=sub_agent AGENT_DOMAIN=crm    uvicorn main:app --port 8003
```

```bash
cp src/.env.example src/.env      # then fill it in
docker compose -f docker/docker-compose.v2.yml up --build
pytest                            # 72 tests, no database or model needed
```

Endpoints (identical for both roles, so the orchestrator's HTTP client
speaks one protocol whatever is on the other end):

| Method | Path | |
|---|---|---|
| `GET`  | `/api/v1/health` | liveness |
| `POST` | `/api/v1/chat` | ask a question |
| `POST` | `/api/v1/chat/stream` | the same, as NDJSON |
| `POST` | `/api/v1/reset` | clear a conversation (orchestrator) |
| `GET`  | `/api/v1/agents` | which specialists are reachable |

---

## Layout

```
src/
├── main.py                    role-based startup; builds the factories
├── helpers/config.py          every environment variable, typed
├── routes/                    HTTP surface, no logic
├── controllers/               the orchestrator's logic
├── models/                    history, memory, schema metadata, enums
└── stores/
    ├── llm/                   LLM backends behind LLMInterface
    ├── db/                    Postgres pool, RLS-aware
    └── agents/
        ├── AgentInterface.py  what the orchestrator sees
        ├── AgentLoop.py       the shared tool-calling loop
        ├── AgentProviderFactory.py
        ├── specs/             one file per domain — data, not code
        ├── providers/         one class per agent *kind* — code
        ├── tools/             the five SQL tools + validation
        └── prompts/           templates by language
```

---

## Kind vs. domain

The distinction the whole design rests on:

| | varies by | pattern | to add one |
|---|---|---|---|
| **Kind** | code | Provider + Factory | a class in `providers/` and a branch in the factory |
| **Domain** | data | a registry entry | a file in `specs/` |

`hr` and `crm` are both `AgentKind.SQL`. They are two specs over one
implementation — the same loop, the same tools, the same prompt body —
differing only in a table allowlist, a history table, and three prompt
fragments. A third SQL domain is a spec file and nothing else.

A spreadsheet agent would be the other case: genuinely different code,
so a new kind, a new provider class, and no change anywhere else —
including in the orchestrator, which only ever sees `AgentInterface`.

The orchestrator builds its delegation tools *from the registry*, so
registering an agent is what makes it usable. There is no list of
domains anywhere else to keep in sync.

### Adding a SQL domain

1. `stores/agents/specs/sales.py` — a `DomainSpec`
2. add it to `AGENT_REGISTRY` in `specs/__init__.py`
3. add its tables and search-type lists to `models/schema_data.py`
4. add a role and its `GRANT`s in `docker/postgres/least_privilege_roles.v2.sql`
5. add a service and a `SUB_AGENT_URLS` entry in the compose file

Steps 4 and 5 are the ones that actually widen data access — which is
why they are deliberate and separate from the code.

---

## The tools

Five, down from seven.

| tool | |
|---|---|
| `get_tables` | what this agent may query |
| `get_table_schema` | real columns and types, embeddings omitted |
| `get_column_search_type` | semantic / text / operator / datetime, as data |
| `execute_sql` | run one SELECT; paging and counting applied by the code |
| `get_distinct_values` | what a status column really contains |

What changed, and why each change removes a class of failure:

- **The model no longer writes `LIMIT`/`OFFSET`.** They are arguments,
  applied by `execute_sql`. A limit the code applies is a bound; a limit
  in the prompt is a suggestion.
- **No second count query.** The count is derived from the model's own
  query, so the two can never describe different filters.
- **No cursor protocol.** Continuation is `offset=next_offset`. The
  cursor machinery was the largest source of complexity in the previous
  version and never fired in practice.
- **No `embed_query_tool`.** A parameter written `{"embed": "text"}` is
  embedded server-side. That removes an LLM round-trip and the Redis
  vector-token cache it needed — tokens that could expire mid-turn, or
  be minted on a replica that did not serve the next call.
- **`get_column_search_type` returns structured data**, not English
  prose with SQL glued into it for the model to re-parse.

---

## SQL safety, in three layers

1. **`sql_validation.py`** parses each statement with `sqlglot` and walks
   the tree — one statement, `SELECT`/`WITH`/`UNION` only, tables inside
   the domain, no raw vector column returned, no dangerous function. A
   structural walk finds every reference regardless of nesting; a token
   scan only catches the shapes someone thought to test.
2. **Least-privilege roles.** `app_hr` cannot see CRM's tables at all.
   This is what makes a bug in layer 1 an error message rather than a
   breach.
3. **Row-level security**, once authentication lands. `PGClient.acquire`
   already pins a principal onto the connection, and every SQL path goes
   through it, so enabling it is a config change (`RLS_ENABLED=true`)
   plus policies — not an audit of every call site.

Three rules in layer 1 were fixed, each a real defect:

- The embed-column rule rejected *any* reference to an `embed_*` column,
  including in `WHERE` and `ORDER BY` — exactly where a pgvector search
  must reference it. The prompts told the model to write
  `embed_name <=> $1::vector` and the validator then rejected it, so
  semantic search could never run. The rule is now what was actually
  meant: never *return* a raw vector; a distance computed from one is a
  number and is fine.
- `SELECT *` was rejected by matching any star anywhere, which also
  rejected `COUNT(*)` — the one thing every count query needs.
- Validation ran against the lowercased query, and the lowercased string
  was what got executed, silently turning `WHERE status = 'Active'` into
  `'active'`.

---

## History and memory

One table per domain holds every event of every turn. The final-answer
row carries two views of the same run:

- **`trace`** — every tool call *with* its result. The audit record.
- **`shape`** — the same calls with results removed. What the semantic
  memory replays as few-shot examples.

The separation is the point. An example teaches by showing which tools
ran, in what order, with what SQL — that is entirely in the shape.
Replaying the rows as well would put one user's query results into
another user's prompt, which is a data leak with nothing gained. The
memory query selects `payload -> 'shape'` explicitly, never the whole
row.

`valid` is computed from the turn's outcome, not curated by hand, and is
stamped onto the turn's user row once the turn finishes — validity
cannot be known when the question is first logged.

---

## Self-hosting the model

The LLM sits behind `LLMInterface`, and `OpenAICompatProvider` speaks
the protocol that both the hosted API and vLLM use. Moving to a local
model is:

```diff
- LLM_API_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
+ LLM_API_URL=http://vllm:8000/v1
```

`EMBEDDING_MODEL_SIZE=1024` matches both `text-embedding-v3` and
`bge-m3`, so self-hosting embeddings later needs no reindexing.

---

## Known gaps

- **No authentication.** `/api/v1/chat` is open. `X-Principal` is read
  from a header the edge sets (and nginx clears from client requests),
  and threaded all the way to the database session — but nothing signs
  or verifies it yet, so `RLS_ENABLED` stays `false`.
- **`schema_data.py` is hand-maintained** and will drift. The column and
  type half should be generated from `information_schema` at startup;
  only the search-type lists genuinely cannot be derived. Two tables
  already show the drift: `directors_employees` and `customers_deals`
  mark columns as semantic that have no `embed_*` companion, so
  `get_column_search_type` downgrades those to text search rather than
  sending the model to query a column that does not exist.
- **`brokers` is not in the HR domain.** The old HR prompt described it
  and the old orchestrator tool advertised it, but it was never in the
  allowlist and never granted — so every broker question failed. The
  prompt now matches the grant. Widening the domain is a data-access
  decision: add it to the spec *and* to the roles file.
- **No eval harness over `Q_test.json` yet.** The 72 tests here cover
  the machinery. The question set is what would cover the answers.
