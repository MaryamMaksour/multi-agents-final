# agent3-service-sales-payments/agent_config.py
from agent_common.config import AgentConfig
from agent_common.history_repo import build_history_repo
from agent_common.rag_agent import build_rag_agent
from agent_common.service import AgentService
from agent_common.tools import build_domain_tools

from main.static import domain

from .prompt import system_prompt

DOMAIN_LABEL = "sales_payments"
ALLOWED_TABLES = domain[9]

history_repo = build_history_repo(table_name="history_sales_payments")

tools = build_domain_tools(allowed_tables=ALLOWED_TABLES, log_sql_query=history_repo.log_sql_query)
tools_dict = {t.name: t for t in tools}


def get_tools():
    return tools


def get_tools_dict():
    return tools_dict


run_agent = build_rag_agent(
    tools=tools,
    tools_dict=tools_dict,
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
    description="Sales & Payments sub-agent microservice for deterministic data retrieval",
    error_label="Sales/Payments",
    agent_service=agent_service,
    ensure_history_schema=history_repo.ensure_history_schema,
)
