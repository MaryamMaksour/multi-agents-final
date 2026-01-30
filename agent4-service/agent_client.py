# agent_client.py
import os
import uuid
import requests

class AgentClient:
    
    def __init__(self, api_base: str | None = None, session_id: str | None = None, timeout: int = 60):
        self.api_base = api_base or os.getenv("AGENT_API_BASE", "http://localhost:8004")

        self.chat_endpoint = f"{self.api_base}/chat"
        self.reset_endpoint = f"{self.api_base}/reset"
        self.health_endpoint = f"{self.api_base}/health"

        self.session_id = session_id or str(uuid.uuid4())
        self.timeout = timeout  # seconds
        self.messages = []


    def health(self) -> dict:
        r = requests.get(self.health_endpoint, timeout=5)
        r.raise_for_status()
        return r.json()


    def new_session(self) -> str:
        self.session_id = str(uuid.uuid4())
        self.messages = []
        return self.session_id

    def chat(self, user_input: str, cursor: str) -> str:
        payload = {"session_id": self.session_id, "user_input": user_input, "context": {"cursor": cursor}}


        r = requests.post(self.chat_endpoint, json=payload, timeout=self.timeout)
        if r.status_code != 200:
            raise RuntimeError(f"API error {r.status_code}: {r.text}")

        data = r.json()
        answer = data.get("answer", "No answer returned.")
        self.messages.append({"role": "assistant", "content": answer})
        return answer
    
