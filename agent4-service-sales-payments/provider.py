# agent4-service-sales-payments/provider.py
from controllers.factory import create_sub_agent
from controllers.provider import ProviderSpec

from helpers.static import domain

from .prompt import system_prompt

DOMAIN_LABEL = "sales_payments"

spec = ProviderSpec(
    key="sales_payments",
    title="Agentic Sub-code-Agent Service",
    description="Sales & Payments sub-agent microservice for deterministic data retrieval",
    error_label="Sales/Payments",
    domain_label=DOMAIN_LABEL,
    table_name="history_sales_payments",
    allowed_tables=domain[7],
    system_prompt=system_prompt,
)

config, tools, tools_dict = create_sub_agent(spec)
agent_service = config.agent_service


def get_tools():
    return tools


def get_tools_dict():
    return tools_dict
