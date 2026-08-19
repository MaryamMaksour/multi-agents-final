# tasks/agent_chat.py
#
# Thin Celery adapter around each service's existing `agent_service.achat(...)`.
# No agent/orchestration/tool logic lives here - each task just imports the
# `agent_service` object from its service package and awaits it. For the 3
# sub-agent services that object is built by agent_config.py (wiring the
# shared agent_common package to this domain's tools/prompt); the
# orchestrator still builds its own in service.py.
#
# Service package names contain hyphens (e.g. "agents-service"), which are not
# valid Python identifiers, so they must be loaded with importlib.import_module
# instead of a normal `from ... import ...` statement.

import asyncio
import importlib
from typing import Any, Dict, Optional

from celery_app import celery_app

_SERVICE_MODULES = {
    "orchestrator": "agents-service.service",
    "property_deals": "agent1-service-property-deals.agent_config",
    "people": "agent2-service-people.agent_config",
    "sales_payments": "agent3-service-sales-payments.agent_config",
}


def _get_agent_service(key: str):
    module = importlib.import_module(_SERVICE_MODULES[key])
    return module.agent_service


def _run_chat(key: str, session_id: str, user_input: Any, context: Optional[Dict[str, Any]]):
    agent_service = _get_agent_service(key)
    return asyncio.run(agent_service.achat(session_id=session_id, user_input=user_input, context=context))


@celery_app.task(
    bind=True, name="tasks.agent_chat.run_orchestrator_chat",
    autoretry_for=(Exception,), retry_kwargs={"max_retries": 3, "countdown": 60}
)
def run_orchestrator_chat(self, session_id: str, user_input: Any, context: Optional[Dict[str, Any]] = None):
    return _run_chat("orchestrator", session_id, user_input, context)


@celery_app.task(
    bind=True, name="tasks.agent_chat.run_property_deals_chat",
    autoretry_for=(Exception,), retry_kwargs={"max_retries": 3, "countdown": 60}
)
def run_property_deals_chat(self, session_id: str, user_input: Any, context: Optional[Dict[str, Any]] = None):
    return _run_chat("property_deals", session_id, user_input, context)


@celery_app.task(
    bind=True, name="tasks.agent_chat.run_people_chat",
    autoretry_for=(Exception,), retry_kwargs={"max_retries": 3, "countdown": 60}
)
def run_people_chat(self, session_id: str, user_input: Any, context: Optional[Dict[str, Any]] = None):
    return _run_chat("people", session_id, user_input, context)


@celery_app.task(
    bind=True, name="tasks.agent_chat.run_sales_payments_chat",
    autoretry_for=(Exception,), retry_kwargs={"max_retries": 3, "countdown": 60}
)
def run_sales_payments_chat(self, session_id: str, user_input: Any, context: Optional[Dict[str, Any]] = None):
    return _run_chat("sales_payments", session_id, user_input, context)
