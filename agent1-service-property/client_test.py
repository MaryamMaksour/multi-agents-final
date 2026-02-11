
from .agent_client import AgentClient

client = AgentClient(  timeout=36000)  # match your long timeout if needed

print("Health:", client.health())

answer = client.chat(" what are the projects in Business Bay",cursor = '' )
print("Assistant:", answer)


