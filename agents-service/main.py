
# main.py (V1-aligned FastAPI app)
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Dict, Optional
from fastapi.responses import StreamingResponse
import json
import asyncio

from .service import agent_service
from .history_repo import ensure_history_schema

from celery_app import celery_app
from celery.result import AsyncResult
from tasks.agent_chat import run_orchestrator_chat
from utils.metrics import setup_metrics

app = FastAPI(
    title="Agentic RAG Agents Service",
    version="1.1.0",
    description="FastAPI microservice for async agentic RAG with Phoenix instrumentation and pagination context",
)

setup_metrics(app)

# =========================
# Schemas
# =========================
class ChatRequest(BaseModel):
    session_id: str = Field(..., description="Conversation session ID")
    user_input: str = Field(..., description="User message to the agent")
    context: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Opaque context propagated by orchestrator (e.g., pagination cursor)",
    )

class ChatResponse(BaseModel):
    session_id: str
    answer: Any  # structured JSON or {"text": "..."} fallback
    history_length: int

class ResetRequest(BaseModel):
    session_id: str

class ResetResponse(BaseModel):
    session_id: str
    status: str

class AsyncChatAccepted(BaseModel):
    task_id: str
    status: str

# =========================
# Health
# =========================
@app.get("/health")
async def health():
    return {"status": "ok"}

# =========================
# Chat (non-streaming)
# =========================
@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Async endpoint:
    - Accepts opaque `context` (e.g., tool cursors) and passes through to the agent.
    - Returns JSON-safe answer (dict/list) or {"text": "..."}.
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
            history_length=await agent_service.history_length(request.session_id),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")

# =========================
# Reset session
# =========================
@app.post("/reset", response_model=ResetResponse)
async def reset(req: ResetRequest):
    try:
        await agent_service.areset(req.session_id)
        return ResetResponse(session_id=req.session_id, status="reset")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reset: {str(e)}")

# =========================
# Chat (async, via Celery)
# =========================
@app.post("/chat/async", response_model=AsyncChatAccepted)
async def chat_async(request: ChatRequest):
    """Queue the chat turn as a Celery task instead of awaiting it inline."""
    task = run_orchestrator_chat.delay(request.session_id, request.user_input, request.context)
    return AsyncChatAccepted(task_id=task.id, status="queued")

@app.get("/chat/status/{task_id}")
async def chat_status(task_id: str):
    result = AsyncResult(task_id, app=celery_app)
    payload: Dict[str, Any] = {"task_id": task_id, "status": result.status}
    if result.ready():
        payload["result"] = result.result if result.successful() else str(result.result)
    return payload

# =========================
# Streaming (NDJSON)
# =========================
@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    Streaming endpoint (NDJSON).
    - If answer is structured (dict/list) -> send once: {"data": ...}
    - Else stream tokens: {"token": "..."} lines, then {"event": "end"}
    """

    async def token_generator():
        try:
            answer = await agent_service.achat(
                session_id=request.session_id,
                user_input=request.user_input,
                context=request.context,
            )

            # Structured payload -> single frame
            if isinstance(answer, (dict, list)):
                yield (json.dumps({"data": answer}) + "\n").encode("utf-8")
                yield (json.dumps({"event": "end"}) + "\n").encode("utf-8")
                return

            # Text fallback -> tokenized
            for chunk in split_into_chunks(str(answer), size=40):
                yield (json.dumps({"token": chunk}) + "\n").encode("utf-8")
                await asyncio.sleep(0.02)

            yield (json.dumps({"event": "end"}) + "\n").encode("utf-8")
        except Exception as e:
            yield (json.dumps({"error": str(e)}) + "\n").encode("utf-8")

    def split_into_chunks(text: str, size: int = 40):
        for i in range(0, len(text), size):
            yield text[i : i + size]

    return StreamingResponse(token_generator(), media_type="application/x-ndjson")

# =========================
# Startup
# =========================
@app.on_event("startup")
async def _startup():
    await ensure_history_schema()
