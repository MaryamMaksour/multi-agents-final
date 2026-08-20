
# agent2-service-hr/main.py
from routes.agent_app import create_agent_app

from .provider import config

app = create_agent_app(config)
