# agent_common/factory.py
#
# The factory: takes one ProviderSpec (a domain's table allowlist, prompt,
# and labels) and wires up everything a sub-agent service needs - the
# history repo bound to its own table, the SQL-executing tool set scoped
# to its own tables, the LangGraph agent built from its own prompt, and the
# request-handling facade - returning a ready-to-serve AgentConfig plus the
# tool list/dict (each service's main.py needs those for its own imports).
#
# Every provider directory's provider.py should be a thin ~20-line file
# that builds one ProviderSpec and calls create_sub_agent() on it. None of
# the wiring below is domain-specific; it's identical for every provider.
from __future__ import annotations

from typing import Tuple

from .config import AgentConfig
from .history_repo import build_history_repo
from .rag_agent import build_rag_agent
from .service import AgentService
from .tools import build_domain_tools
from .provider import ProviderSpec


def create_sub_agent(provider: ProviderSpec) -> Tuple[AgentConfig, list, dict]:
    """
    Builds a fully-wired AgentConfig for `provider`.
    Returns (config, tools, tools_dict) - the latter two are what each
    service's provider.py re-exports as get_tools()/get_tools_dict().
    """
    history_repo = build_history_repo(table_name=provider.table_name)

    tools = build_domain_tools(
        allowed_tables=provider.allowed_tables,
        log_sql_query=history_repo.log_sql_query,
    )
    tools_dict = {t.name: t for t in tools}

    run_agent = build_rag_agent(
        tools=tools,
        tools_dict=tools_dict,
        system_prompt=provider.system_prompt,
        domain_label=provider.domain_label,
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
        title=provider.title,
        description=provider.description,
        error_label=provider.error_label,
        agent_service=agent_service,
        ensure_history_schema=history_repo.ensure_history_schema,
    )

    return config, tools, tools_dict
