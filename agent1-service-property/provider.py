# agent1-service-property/provider.py
from controllers.factory import create_sub_agent
from controllers.provider import ProviderSpec

from helpers.static import domain

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
