"""Request and response shapes for the chat endpoints.

Validation lives here, as a Pydantic model passed into the route, so a
malformed request is rejected before any handler code runs.
"""
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str = Field(..., min_length=1, description="Conversation session ID")
    user_input: str = Field(..., min_length=1, description="The user's question")
    context: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional call context, e.g. {'offset': 20} to continue a result set",
    )


class ChatResponse(BaseModel):
    session_id: str
    answer: Any
    history_length: int = 0


class ResetRequest(BaseModel):
    session_id: str = Field(..., min_length=1)


class ResetResponse(BaseModel):
    session_id: str
    status: str
