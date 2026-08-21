"""Turns a LangGraph message list into a readable list of steps.

Produces two views of the same run, because they are wanted for
different purposes and must not be confused:

  trace  every tool call with its arguments *and* its result. This is
         the audit record.
  shape  the same calls with results removed. This is what may be
         replayed into a future prompt as a worked example.

Keeping them apart is what lets the memory show the model how a similar
question was answered without also showing it that question's data.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

# Arguments that describe the request rather than the query, and would
# be noise in an example.
_NOISE_ARGS = ("session_id", "turn_id", "principal")


def _parse_maybe_json(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("(") and text.endswith(")"):
            text = text[1:-1].strip()
        try:
            return json.loads(text)
        except Exception:
            return text
    return value


def _clean_args(args: Dict[str, Any]) -> Dict[str, Any]:
    cleaned = dict(args or {})
    for key in _NOISE_ARGS:
        cleaned.pop(key, None)
    return cleaned


def extract_pipeline(messages: List[Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Returns (trace, shape) for one agent run."""
    pending: Dict[str, Dict[str, Any]] = {}
    trace: List[Dict[str, Any]] = []
    shape: List[Dict[str, Any]] = []

    for message in messages:
        tool_calls = getattr(message, "tool_calls", None)
        if tool_calls:
            for call in tool_calls:
                pending[call.get("id")] = {
                    "name": call.get("name"),
                    "args": call.get("args") or {},
                }
            continue

        tool_call_id = getattr(message, "tool_call_id", None)
        tool_name = getattr(message, "name", None)
        if tool_call_id and (tool_name or tool_call_id in pending):
            info = pending.pop(tool_call_id, {"name": tool_name, "args": {}})
            args = _clean_args(info.get("args", {}))
            name = info.get("name") or tool_name
            result = _parse_maybe_json(getattr(message, "content", ""))

            trace.append({"type": "tool", "name": name, "args": args, "result": result})

            # The shape records that the call was made and how it was
            # parameterized - never what came back.
            step: Dict[str, Any] = {"type": "tool", "name": name, "args": args}
            if isinstance(result, dict) and result.get("error"):
                # An error is about the call, not about the data, and is
                # the whole point of a counter-example.
                step["error"] = result["error"]
            shape.append(step)
            continue

    if messages:
        content = getattr(messages[-1], "content", None)
        if content not in (None, ""):
            answer = _parse_maybe_json(content)
            trace.append({"type": "final", "answer": answer})
            shape.append({"type": "final"})

    return trace, shape
