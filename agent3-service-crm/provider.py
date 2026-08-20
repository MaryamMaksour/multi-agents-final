# agent3-service-crm/provider.py
from agent_common.factory import create_sub_agent
from agent_common.provider import ProviderSpec

from main.static import domain

from .prompt import system_prompt

spec = ProviderSpec(
    key="crm",
    title="Agentic Sub-code-Agent Service",
    description="CRM sub-agent microservice for deterministic data retrieval",
    error_label="CRM",
    domain_label="crm",
    table_name="history_crm",
    allowed_tables=domain[3],
    system_prompt=system_prompt,
)

config, tools, tools_dict = create_sub_agent(spec)
agent_service = config.agent_service


def get_tools():
    return tools


def get_tools_dict():
    return tools_dict
