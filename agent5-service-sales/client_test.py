
from .agent_client import AgentClient

client = AgentClient(  timeout=36000)  # match your long timeout if needed

print("Health:", client.health())

answer = client.chat("Are there bookings with unusually high or low prices indicating anomalies",cursor = '' )
print("Assistant:", answer)


