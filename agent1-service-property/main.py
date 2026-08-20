
# agent1-service-property/main.py
from agent_common.app import create_agent_app

from .provider import config

app = create_agent_app(config)
