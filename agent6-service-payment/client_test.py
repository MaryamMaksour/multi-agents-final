
from .agent_client import AgentClient

client = AgentClient(  timeout=36000)  # match your long timeout if needed

print("Health:", client.health())

answer = client.chat("How many payments were made by cheque this month?  ",cursor = '' )
print("Assistant:", answer)


