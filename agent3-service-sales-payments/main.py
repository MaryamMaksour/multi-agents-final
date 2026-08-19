
# agent3-service-sales-payments/main.py
from agent_common.app import create_agent_app

from celery_app import celery_app
from tasks.agent_chat import run_sales_payments_chat

from .agent_config import config

app = create_agent_app(config, async_task=run_sales_payments_chat, celery_app=celery_app)
