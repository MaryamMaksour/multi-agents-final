"""HTTP entry points for both roles.

Routes stay thin on purpose: validate, call a controller, shape a
response. The previous orchestrator's main.py held the streaming logic,
the envelope building and the error handling inline, which made all of
it unreachable from a test that did not go through HTTP.

The same module serves both roles. An orchestrator process has
`app.orchestrator` set; a sub-agent process has `app.agent`. Both expose
/api/v1/chat, so the orchestrator's HTTP client speaks one protocol
regardless of what is on the other end.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from models.enums import ResponseSignal
from routes.schemes.chat import ChatRequest, ChatResponse, ResetRequest, ResetResponse

logger = logging.getLogger(__name__)

chat_router = APIRouter(prefix="/api/v1", tags=["chat", "api_v1"])


def _principal_of(request: Request) -> Optional[str]:
    """The authenticated caller, once authentication is added.

    Read from a header the edge sets, never from the request body: a
    body field is something the model - or anyone posting to this
    endpoint - can choose for itself. Until the edge authenticates and
    signs this, it stays advisory and RLS_ENABLED stays off.
    """
    return request.headers.get("X-Principal")


async def _answer(request: Request, payload: ChatRequest) -> Any:
    orchestrator = getattr(request.app, "orchestrator", None)
    if orchestrator is not None:
        return await orchestrator.achat(
            session_id=payload.session_id,
            user_input=payload.user_input,
            principal=_principal_of(request),
        )

    agent = getattr(request.app, "agent", None)
    if agent is None:
        raise HTTPException(status_code=503, detail="This process has no agent configured.")

    return await agent.ainvoke(
        query=payload.user_input,
        session_id=payload.session_id,
        offset=int((payload.context or {}).get("offset", 0) or 0),
        principal=_principal_of(request),
    )


@chat_router.post("/chat", response_model=ChatResponse)
async def chat(request: Request, payload: ChatRequest):
    try:
        answer = await _answer(request, payload)
    except HTTPException:
        raise
    except Exception:
        # The reason goes to the logs; the caller gets a signal. Error
        # text from a failed query can name tables and columns.
        logger.exception("Chat failed for session %s", payload.session_id)
        return JSONResponse(
            status_code=500,
            content={"signal": ResponseSignal.CHAT_FAILED.value},
        )

    orchestrator = getattr(request.app, "orchestrator", None)
    history_length = (
        await orchestrator.history_length(payload.session_id) if orchestrator else 0
    )

    return ChatResponse(
        session_id=payload.session_id,
        answer=answer,
        history_length=history_length,
    )


@chat_router.post("/chat/stream")
async def chat_stream(request: Request, payload: ChatRequest):
    """NDJSON stream.

    A structured answer is one frame - splitting JSON into 40-character
    chunks would just force the client to reassemble it. Only plain text
    is chunked.
    """

    async def frames():
        try:
            answer = await _answer(request, payload)

            if isinstance(answer, (dict, list)):
                yield (json.dumps({"data": answer}, ensure_ascii=False, default=str) + "\n").encode()
            else:
                text = str(answer)
                for index in range(0, len(text), 40):
                    yield (json.dumps({"token": text[index:index + 40]}, ensure_ascii=False) + "\n").encode()
                    await asyncio.sleep(0.02)

            yield (json.dumps({"event": "end"}) + "\n").encode()

        except Exception:
            logger.exception("Streaming chat failed for session %s", payload.session_id)
            yield (json.dumps({"signal": ResponseSignal.CHAT_FAILED.value}) + "\n").encode()

    return StreamingResponse(frames(), media_type="application/x-ndjson")


@chat_router.post("/reset", response_model=ResetResponse)
async def reset(request: Request, payload: ResetRequest):
    orchestrator = getattr(request.app, "orchestrator", None)
    if orchestrator is None:
        return ResetResponse(session_id=payload.session_id, status="noop")

    await orchestrator.areset(payload.session_id)
    return ResetResponse(session_id=payload.session_id, status="reset")


@chat_router.get("/agents")
async def agents(request: Request):
    """What this orchestrator can delegate to, and whether it is reachable."""
    orchestrator = getattr(request.app, "orchestrator", None)
    if orchestrator is None:
        return {"agents": []}

    checks = await asyncio.gather(
        *(agent.health() for agent in orchestrator.agents.values()),
        return_exceptions=True,
    )
    return {
        "agents": [
            check if isinstance(check, dict) else {"status": "error", "detail": str(check)}
            for check in checks
        ]
    }
