# agent2-service-hr/provider.py
from controllers.factory import create_sub_agent
from controllers.provider import ProviderSpec

from helpers.static import domain

from .prompt import system_prompt

spec = ProviderSpec(
    key="hr",
    title="Agentic Sub-code-Agent Service",
    description="HR / Organization sub-agent microservice for deterministic data retrieval",
    error_label="Organization",
    domain_label="hr",
    table_name="history_hr",
    allowed_tables=domain[2],
    system_prompt=system_prompt,
)

config, tools, tools_dict = create_sub_agent(spec)
agent_service = config.agent_service


def get_tools():
    return tools


def get_tools_dict():
    return tools_dict
