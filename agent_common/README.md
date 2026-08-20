# agent-common

Shared scaffolding extracted from the near-identical sub-agent services.
Before this package existed, every sub-agent service carried its own
byte-for-byte copy of `main.py`, `service.py`, `running_agent.py`,
`RAG_Agent.py`, and `history_repo_1.py` - differing only in a handful of
parameters (a table name, an error-message label, the domain's
tools/prompt). This package is that shared implementation, parameterized
instead of copy-pasted, wired together by a factory from a small
per-domain provider spec.

## What's here

- `provider.py` - `ProviderSpec`: the dataclass a domain fills in to
  describe itself (key, title, description, error label, domain label,
  history table name, allowed tables, system prompt). This is "the
  provider" for a domain.
- `factory.py` - `create_sub_agent(provider: ProviderSpec)`: "the
  factory" - the single wiring point that turns a `ProviderSpec` into a
  ready `(AgentConfig, tools, tools_dict)` tuple, building the history
  repo, domain tools, RAG agent loop, and agent service underneath.
- `history_repo.py` - `build_history_repo(table_name)`: the history-logging
  API (schema, user/assistant/tool-call logging, semantic memory lookup),
  bound to one Postgres table.
- `rag_agent.py` - `build_rag_agent(tools, tools_dict, system_prompt,
  domain_label, get_memory, log_tool_call)`: builds the LangGraph
  tool-calling loop, returning an async `run_agent(messages)` callable.
- `tools.py` - `build_domain_tools(allowed_tables, log_sql_query)`: the
  shared DB tool set (db_execute, get_table_schema, get_filter, etc.),
  scoped to one domain's table allowlist.
- `service.py` - `AgentService`: the stateless chat request-handling facade
  (envelope building, final-answer extraction, turn logging), constructed
  from a `run_agent` callable plus the history-logging functions.
- `app.py` - `create_agent_app(config)`: builds the FastAPI app (`/health`,
  `/chat`, `/chat/stream`), plus the Prometheus metrics endpoint.
- `config.py` - `AgentConfig`: the small dataclass tying the above together
  for one domain.
- `sql_validation.py` - AST-based (sqlglot) validation of LLM-authored SQL:
  single SELECT/WITH/UNION statement, table allowlist, no `embed_*`
  columns, no dangerous functions.

## What's NOT here

Each service keeps its own `prompt.py` (domain-specific system prompt) -
that's real business logic, not boilerplate, and was never duplicated in
the first place.

## Runtime dependency on `main/`

This package imports `main.llm`, `main.conect_to_DB`, `main.embeddings`,
and `main.pipeline_utils` from the repo's top-level `main/` package at
runtime. It is installable and versionable on its own, but it still
expects a `main` package to be importable alongside it - same coupling
every sub-agent service already had before this refactor.

## Usage

A service's `provider.py` is a small file (~25 lines) supplying a
`ProviderSpec` to the factory:

```python
from agent_common.factory import create_sub_agent
from agent_common.provider import ProviderSpec

from main.static import domain

from .prompt import system_prompt

spec = ProviderSpec(
    key="property",
    title="Agentic Sub-code-Agent Service",
    description="Property sub-agent microservice for deterministic data retrieval",
    error_label="property",
    domain_label="property",
    table_name="history_property",
    allowed_tables=domain[1],
    system_prompt=system_prompt,
)

config, tools, tools_dict = create_sub_agent(spec)
agent_service = config.agent_service


def get_tools():
    return tools


def get_tools_dict():
    return tools_dict
```

Then `main.py` is just:

```python
from agent_common.app import create_agent_app

from .provider import config

app = create_agent_app(config)
```
