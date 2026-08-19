
# sub-agent1/main.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Dict, Optional
from fastapi.responses import StreamingResponse
import json
import asyncio

from .service import agent_service

from .history_repo_1 import ensure_history_schema

from celery_app import celery_app
from celery.result import AsyncResult
from tasks.agent_chat import run_hr_chat
from utils.metrics import setup_metrics

app = FastAPI(
    title="Agentic Sub-code-Agent Service",
    version="1.0.0",
    description="Sub-code-agent microservice for deterministic data retrieval",
)

setup_metrics(app)

# =====================================================
# Schemas
# =====================================================
class ChatRequest(BaseModel):
    session_id: str = Field(..., description="Conversation session ID")
    user_input: str = Field(..., description="User query or continuation request")
    context: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Opaque context from orchestrator (e.g. cursor)"
    )

class ChatResponse(BaseModel):
    session_id: str
    answer: Any
    history_length: int

class ResetRequest(BaseModel):
    session_id: str

class ResetResponse(BaseModel):
    session_id: str
    status: str

class AsyncChatAccepted(BaseModel):
    task_id: str
    status: str


# =====================================================
# Health
# =====================================================
@app.get("/health")
async def health():
    return {"status": "ok"}


# =====================================================
# Chat (NON‑Streaming)
# =====================================================
@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Async endpoint:
    - Accepts opaque context (cursor).
    - Does NOT interpret or modify it.
    - Returns JSON-only answer from sub-agent.
    """
    try:
        answer = await agent_service.achat(
            session_id=request.session_id,
            user_input=request.user_input,
            context=request.context,
        )
        return ChatResponse(
            session_id=request.session_id,
            answer=answer,
            history_length=1,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Organization Sub‑agent execution failed: {str(e)}"
        )


# =====================================================
# Chat (async, via Celery)
# =====================================================
@app.post("/chat/async", response_model=AsyncChatAccepted)
async def chat_async(request: ChatRequest):
    """Queue the chat turn as a Celery task instead of awaiting it inline."""
    task = run_hr_chat.delay(request.session_id, request.user_input, request.context)
    return AsyncChatAccepted(task_id=task.id, status="queued")

@app.get("/chat/status/{task_id}")
async def chat_status(task_id: str):
    result = AsyncResult(task_id, app=celery_app)
    payload: Dict[str, Any] = {"task_id": task_id, "status": result.status}
    if result.ready():
        payload["result"] = result.result if result.successful() else str(result.result)
    return payload

# =====================================================
# Streaming Chat (NDJSON)
# =====================================================
@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    Streaming endpoint.
    - Structured JSON responses are sent as a SINGLE event: {"data": ...}
    - Token streaming is only for plain text fallback.
    """

    async def token_generator():
        try:
            answer = await agent_service.achat(
                session_id=request.session_id,
                user_input=request.user_input,
                context=request.context,
            )

            # If structured JSON → send once
            if isinstance(answer, (dict, list)):
                yield (json.dumps({"data": answer}) + "\n").encode("utf-8")
                yield (json.dumps({"event": "end"}) + "\n").encode("utf-8")
                return

            # Fallback: stream text chunks
            for chunk in split_into_chunks(str(answer), 40):
                yield (json.dumps({"token": chunk}) + "\n").encode("utf-8")
                await asyncio.sleep(0.02)

            yield (json.dumps({"event": "end"}) + "\n").encode("utf-8")

        except Exception as e:
            yield (json.dumps({"error": str(e)}) + "\n").encode("utf-8")

    def split_into_chunks(text: str, size: int):
        for i in range(0, len(text), size):
            yield text[i:i + size]

    return StreamingResponse(token_generator(), media_type="application/x-ndjson")

# =====================================================
# History
# =====================================================

@app.on_event("startup")
async def _startup():
    await ensure_history_schema()
 