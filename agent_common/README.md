# agent-common

Shared scaffolding extracted from the 6 near-identical sub-agent services
(`agent1-service-property` .. `agent6-service-payment`). Before this package
existed, every one of those services carried its own byte-for-byte copy of
`main.py`, `service.py`, `running_agent.py`, `RAG_Agent.py`, and
`history_repo_1.py` - differing only in a handful of parameters (a table
name, an error-message label, the domain's tools/prompt). This package is
that shared implementation, parameterized instead of copy-pasted.

## What's here

- `history_repo.py` - `build_history_repo(table_name)`: the history-logging
  API (schema, user/assistant/tool-call logging, semantic memory lookup),
  bound to one Postgres table.
- `rag_agent.py` - `build_rag_agent(tools, tools_dict, system_prompt,
  domain_label, get_memory, log_tool_call)`: builds the LangGraph
  tool-calling loop, returning an async `run_agent(messages)` callable.
- `service.py` - `AgentService`: the stateless chat request-handling facade
  (envelope building, final-answer extraction, turn logging), constructed
  from a `run_agent` callable plus the history-logging functions.
- `app.py` - `create_agent_app(config, async_task=None, celery_app=None)`:
  builds the FastAPI app (`/health`, `/chat`, `/chat/stream`, and
  optionally `/chat/async` + `/chat/status/{task_id}` when a Celery task is
  supplied), plus the Prometheus metrics endpoint.
- `config.py` - `AgentConfig`: the small dataclass tying the above together
  for one domain.

## What's NOT here

Each service keeps its own `tools.py` (domain-specific DB queries/tools)
and `prompt.py` (domain-specific system prompt) - those are real business
logic, not boilerplate, and were never duplicated in the first place.

## Runtime dependency on `main/`

This package imports `main.llm`, `main.conect_to_DB`, `main.embeddings`,
and `main.pipeline_utils` from the repo's top-level `main/` package at
runtime. It is installable and versionable on its own, but it still
expects a `main` package to be importable alongside it - same coupling
every sub-agent service already had before this refactor.

## Usage

A service's `agent_config.py` wires the domain-specific pieces together:

```python
from agent_common.config import AgentConfig
from agent_common.history_repo import build_history_repo
from agent_common.rag_agent import build_rag_agent
from agent_common.service import AgentService

from .agent_tools import get_tools, get_tools_dict
from .prompt import system_prompt

history_repo = build_history_repo(table_name="history1")

run_agent = build_rag_agent(
    tools=get_tools(),
    tools_dict=get_tools_dict(),
    system_prompt=system_prompt,
    domain_label="property",
    get_memory=history_repo.get_memory,
    log_tool_call=history_repo.log_tool_call,
)

agent_service = AgentService(
    run_agent=run_agent,
    new_turn_id=history_repo.new_turn_id,
    log_user_message=history_repo.log_user_message,
    log_assistant_final=history_repo.log_assistant_final,
)

config = AgentConfig(
    title="Agentic Sub-code-Agent Service",
    description="Sub-code-agent microservice for deterministic data retrieval",
    error_label="property",
    agent_service=agent_service,
    ensure_history_schema=history_repo.ensure_history_schema,
)
```

Then `main.py` is just:

```python
from agent_common.app import create_agent_app
from celery_app import celery_app
from tasks.agent_chat import run_property_chat
from .agent_config import config

app = create_agent_app(config, async_task=run_property_chat, celery_app=celery_app)
```
