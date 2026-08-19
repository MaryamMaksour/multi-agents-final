# agent_common/app.py
#
# Every route here was byte-for-byte identical (bar one error-message
# string) across all 6 sub-agent services' main.py before this was
# extracted. Domain-specific behavior lives entirely in
# `config.agent_service` and `config.ensure_history_schema`.
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .config import AgentConfig


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


def _split_into_chunks(text: str, size: int = 40):
    for i in range(0, len(text), size):
        yield text[i:i + size]


def create_agent_app(config: AgentConfig, async_task=None, celery_app=None) -> FastAPI:
    """
    Builds a sub-agent FastAPI app from `config`.

    `async_task`/`celery_app`: when both are supplied, adds `/chat/async`
    (queues the turn as a Celery task) and `/chat/status/{task_id}`.
    """
    app = FastAPI(
        title=config.title,
        version="1.0.0",
        description=config.description,
    )

    try:
        from utils.metrics import setup_metrics
        setup_metrics(app)
    except ImportError:
        pass

    agent_service = config.agent_service

    @app.get("/health")
    async def health():
        return {"status": "ok"}

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
                detail=f"{config.error_label} Sub‑agent execution failed: {str(e)}"
            )

    if async_task is not None and celery_app is not None:
        from celery.result import AsyncResult

        @app.post("/chat/async", response_model=AsyncChatAccepted)
        async def chat_async(request: ChatRequest):
            """Queue the chat turn as a Celery task instead of awaiting it inline."""
            task = async_task.delay(request.session_id, request.user_input, request.context)
            return AsyncChatAccepted(task_id=task.id, status="queued")

        @app.get("/chat/status/{task_id}")
        async def chat_status(task_id: str):
            result = AsyncResult(task_id, app=celery_app)
            payload: Dict[str, Any] = {"task_id": task_id, "status": result.status}
            if result.ready():
                payload["result"] = result.result if result.successful() else str(result.result)
            return payload

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

                # If structured JSON -> send once
                if isinstance(answer, (dict, list)):
                    yield (json.dumps({"data": answer}) + "\n").encode("utf-8")
                    yield (json.dumps({"event": "end"}) + "\n").encode("utf-8")
                    return

                # Fallback: stream text chunks
                for chunk in _split_into_chunks(str(answer), 40):
                    yield (json.dumps({"token": chunk}) + "\n").encode("utf-8")
                    await asyncio.sleep(0.02)

                yield (json.dumps({"event": "end"}) + "\n").encode("utf-8")

            except Exception as e:
                yield (json.dumps({"error": str(e)}) + "\n").encode("utf-8")

        return StreamingResponse(token_generator(), media_type="application/x-ndjson")

    @app.on_event("startup")
    async def _startup():
        await config.ensure_history_schema()

    return app
