"""One entry point, two roles.

There is a single application here, and a single container image. What a
process serves is decided by two environment variables:

    AGENT_ROLE=orchestrator                  -> the main agent
    AGENT_ROLE=sub_agent AGENT_DOMAIN=hr     -> the HR agent
    AGENT_ROLE=sub_agent AGENT_DOMAIN=crm    -> the CRM agent

The previous layout had one directory per service, each holding a
near-identical main.py, service.py and history repo. Beyond the
duplication, it also meant all five services shared one env file - and
therefore one Postgres user - which is why the per-domain least-
privilege roles in docker/postgres/least_privilege_roles.sql were
written but never actually applied. One image with per-deployment
environment is what makes those roles usable.
"""
from __future__ import annotations

import logging

import redis.asyncio as redis_asyncio
from fastapi import FastAPI

from helpers.config import get_settings
from models.enums import AgentRole
from models.HistoryModel import HistoryModel
from routes import base_router, chat_router
from stores.agents import AgentProviderFactory, registered_domains
from stores.agents.prompts import TemplateParser
from stores.db import PGClient
from stores.llm import LLMProviderFactory
from utils.metrics import setup_metrics

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Multi-agent SQL question answering over pgvector",
)
app.settings = settings

setup_metrics(app)


@app.on_event("startup")
async def startup():
    # --- shared clients ------------------------------------------------
    app.pg_client = PGClient(config=settings)
    await app.pg_client.connect()

    llm_factory = LLMProviderFactory(config=settings)

    generation_client = llm_factory.create(settings.GENERATION_BACKEND)
    generation_client.set_generation_model(model_id=settings.GENERATION_MODEL_ID)

    embedding_client = llm_factory.create(settings.EMBEDDING_BACKEND)
    embedding_client.set_embedding_model(
        model_id=settings.EMBEDDING_MODEL_ID,
        embedding_size=settings.EMBEDDING_MODEL_SIZE,
    )

    app.generation_client = generation_client
    app.embedding_client = embedding_client
    app.template_parser = TemplateParser(language="en", default_language="en")

    agent_factory = AgentProviderFactory(
        config=settings,
        pg_client=app.pg_client,
        llm=generation_client,
        embed_text=embedding_client.embed_text,
        template_parser=app.template_parser,
    )
    app.agent_factory = agent_factory

    # --- role-specific wiring ------------------------------------------
    role = (settings.AGENT_ROLE or "").strip().lower()

    if role == AgentRole.SUB_AGENT.value:
        if not settings.AGENT_DOMAIN:
            raise RuntimeError(
                "AGENT_ROLE=sub_agent needs AGENT_DOMAIN set to one of "
                f"{registered_domains()}."
            )
        app.agent = await agent_factory.create(settings.AGENT_DOMAIN)
        logger.info("Serving the %s sub-agent.", app.agent.key)

    elif role == AgentRole.ORCHESTRATOR.value:
        app.redis = redis_asyncio.from_url(settings.REDIS_URL, decode_responses=True)

        # The orchestrator's own history table. It gets no SELECT grant
        # on any business table - it reaches data only by delegating.
        orchestrator_history = await HistoryModel.create_instance(
            pg_client=app.pg_client, config=settings, table_name="history_orchestrator"
        )

        from controllers import OrchestratorController

        agents = agent_factory.create_all_remote()
        app.orchestrator = OrchestratorController(
            config=settings,
            llm=app.generation_client,
            agents=agents,
            template_parser=app.template_parser,
            history_model=orchestrator_history,
            redis=app.redis,
        )
        logger.info("Serving the orchestrator over agents: %s", sorted(agents))

    else:
        raise RuntimeError(
            f"AGENT_ROLE must be 'orchestrator' or 'sub_agent', got {settings.AGENT_ROLE!r}."
        )


@app.on_event("shutdown")
async def shutdown():
    if getattr(app, "pg_client", None):
        await app.pg_client.disconnect()
    if getattr(app, "redis", None):
        await app.redis.aclose()


app.include_router(base_router)
app.include_router(chat_router)
