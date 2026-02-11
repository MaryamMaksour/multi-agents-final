
from .agent_client import AgentClient

client = AgentClient(  timeout=36000)  # match your long timeout if needed

print("Health:", client.health())

answer = client.chat(" the 5 most recent deals ",cursor = '' )
print("Assistant:", answer)


