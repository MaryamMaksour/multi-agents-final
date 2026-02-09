
from .agent_client import AgentClient

client = AgentClient(  timeout=36000)  # match your long timeout if needed

print("Health:", client.health())

answer = client.chat("send all info for payment id = 1",cursor = '' )
print("Assistant:", answer)


