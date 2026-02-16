
from .agent_client import AgentClient

client = AgentClient(  timeout=36000)  # match your long timeout if needed

print("Health:", client.health())

answer = client.chat(" active deals for all units (active or not active) in building ID 12 ",cursor = '' )
print("Assistant:", answer)


