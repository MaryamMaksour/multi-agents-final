
from .agent_client import AgentClient

client = AgentClient(  timeout=36000)  # match your long timeout if needed

print("Health:", client.health())

answer = client.chat(" 1.	Does Unit SHOP 01 in building Sap32 have parking ",cursor = '' )
print("Assistant:", answer)


