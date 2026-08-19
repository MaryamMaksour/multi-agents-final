# agent5-service-sales/agent_config.py
from agent_common.config import AgentConfig
from agent_common.rag_agent import build_rag_agent
from agent_common.service import AgentService

from .agent_tools import get_tools, get_tools_dict
from .history_repo_1 import history_repo
from .prompt import system_prompt

DOMAIN_LABEL = "sales"

run_agent = build_rag_agent(
    tools=get_tools(),
    tools_dict=get_tools_dict(),
    system_prompt=system_prompt,
    domain_label=DOMAIN_LABEL,
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
    error_label="Booking",
    agent_service=agent_service,
    ensure_history_schema=history_repo.ensure_history_schema,
)
