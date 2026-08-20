"""Per-request context for tool calls.

Tools need to know which session and turn they belong to, and - once
authorization lands - which authenticated principal is asking. The
previous design passed `session_id` and `turn_id` as tool *arguments*,
which meant the model had to copy them out of a JSON envelope into every
call. It usually did, and when it did not the call simply went unlogged.

Making them model-supplied arguments is also the wrong shape for an
identity: anything the model can write, a prompt injection can rewrite.
A context variable is set by the controller from the authenticated
request before the graph runs, and tools read it directly - out of the
model's reach, and impossible to forget.
"""
from __future__ import annotations

import contextvars
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class RequestContext:
    session_id: str
    turn_id: str
    # Set from the authenticated request once authentication is added.
    # PGClient.acquire() pins it onto the connection so row-level
    # security policies can key off it.
    principal: Optional[str] = None


_EMPTY = RequestContext(session_id="", turn_id="", principal=None)

_current: contextvars.ContextVar[RequestContext] = contextvars.ContextVar(
    "agent_request_context", default=_EMPTY
)


def set_request_context(context: RequestContext) -> contextvars.Token:
    return _current.set(context)


def reset_request_context(token: contextvars.Token) -> None:
    _current.reset(token)


def get_request_context() -> RequestContext:
    return _current.get()
