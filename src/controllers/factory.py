# controllers/factory.py
from __future__ import annotations

from typing import Tuple

from .agent_config import AgentConfig
from .history_repo import build_history_repo
from .rag_agent import build_rag_agent
from .service import AgentService
from .tools import build_domain_tools
from .provider import ProviderSpec


def create_sub_agent(provider: ProviderSpec) -> Tuple[AgentConfig, list, dict]:
    history_repo = build_history_repo(table_name=provider.table_name)
    tools = build_domain_tools(allowed_tables=provider.allowed_tables, log_sql_query=history_repo.log_sql_query)
    tools_dict = {t.name: t for t in tools}
    run_agent = build_rag_agent(
        tools=tools, tools_dict=tools_dict, system_prompt=provider.system_prompt,
        domain_label=provider.domain_label, get_memory=history_repo.get_memory,
        log_tool_call=history_repo.log_tool_call,
    )
    agent_service = AgentService(
        run_agent=run_agent, new_turn_id=history_repo.new_turn_id,
        log_user_message=history_repo.log_user_message, log_assistant_final=history_repo.log_assistant_final,
    )
    config = AgentConfig(
        title=provider.title, description=provider.description, error_label=provider.error_label,
        agent_service=agent_service, ensure_history_schema=history_repo.ensure_history_schema,
    )
    return config, tools, tools_dict
