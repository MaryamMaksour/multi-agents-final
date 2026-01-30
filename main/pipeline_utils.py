
# main/pipeline_utils.py
from __future__ import annotations

import json
from typing import Any

def _try_parse_json(x: Any) -> Any:
    """Try to parse JSON strings; otherwise return as-is."""
    if isinstance(x, (dict, list)):
        return x
    if isinstance(x, str):
        s = x.strip()
        # normalize "( ... )" wrappers some models output
        if s.startswith("(") and s.endswith(")"):
            s = s[1:-1].strip()
        try:
            return json.loads(s)
        except Exception:
            return s
    return x

def extract_pipeline(messages: list[Any]) -> list[dict]:
    """
    Extracts a clean pipeline:
      tool(name,args) -> tool_result -> ... -> final_answer
    from LangChain messages:
      - AIMessage.tool_calls
      - ToolMessage(tool_call_id,name,content)
      - final AIMessage.content
    """
    # Map tool_call_id -> {name,args}
    pending: dict[str, dict] = {}
    steps: list[dict] = []

    for m in messages:
        # 1) Capture tool calls from AI messages
        tool_calls = getattr(m, "tool_calls", None)
        if tool_calls:
            for tc in tool_calls:
                tc_id = tc.get("id")
                pending[tc_id] = {
                    "name": tc.get("name"),
                    "args": tc.get("args") or {},
                }
            continue

        # 2) Capture tool results from ToolMessage(s)
        # ToolMessage has: tool_call_id, name, content
        tool_call_id = getattr(m, "tool_call_id", None)
        tool_name = getattr(m, "name", None)
        if tool_call_id and (tool_name or tool_call_id in pending):
            info = pending.pop(tool_call_id, {"name": tool_name, "args": {}})
            tool_args = info.get("args", {})
            tool_result = _try_parse_json(getattr(m, "content", ""))

            # Remove correlation keys from args  
            tool_args = dict(tool_args)
            tool_args.pop("session_id", None)
            tool_args.pop("turn_id", None)

            steps.append({
                "type": "tool",
                "name": info.get("name") or tool_name,
                "args": tool_args,
                "result": tool_result,
            })
            continue

    # 3) Final answer is the last AI message content (not tool calls)
    # Usually last message is an AIMessage with content
    if messages:
        last = messages[-1]
        final_content = getattr(last, "content", None)
        if final_content not in (None, ""):
            steps.append({
                "type": "final",
                "answer": _try_parse_json(final_content),
            })

    return steps
 
def extract_pipeline_main(messages: list[Any]) -> list[dict]:
    """
    Extracts a clean pipeline for the main agent:
      tool(name,args) ->   ... -> final_answer
    from LangChain messages:
      - AIMessage.tool_calls
      - ToolMessage(tool_call_id,name,content)
      - final AIMessage.content
    """
    # Map tool_call_id -> {name,args}
    pending: dict[str, dict] = {}
    steps: list[dict] = []

    for m in messages:
        # 1) Capture tool calls from AI messages
        tool_calls = getattr(m, "tool_calls", None)
        if tool_calls:
            for tc in tool_calls:
                tc_id = tc.get("id")
                pending[tc_id] = {
                    "name": tc.get("name"),
                    "args": tc.get("args") or {},
                }
            continue

        # 2) Capture tool results from ToolMessage(s)
        # ToolMessage has: tool_call_id, name, content
        tool_call_id = getattr(m, "tool_call_id", None)
        tool_name = getattr(m, "name", None)
        if tool_call_id and (tool_name or tool_call_id in pending):
            info = pending.pop(tool_call_id, {"name": tool_name, "args": {}})
            tool_args = info.get("args", {})

            # Remove correlation keys from args  
            tool_args = dict(tool_args)
            tool_args.pop("session_id", None)
            tool_args.pop("turn_id", None)

            steps.append({
                "type": "tool",
                "name": info.get("name") or tool_name,
                "args": tool_args
            })
            continue

    # 3) Final answer is the last AI message content (not tool calls)
    # Usually last message is an AIMessage with content
    if messages:
        last = messages[-1]
        final_content = getattr(last, "content", None)
        if final_content not in (None, ""):
            steps.append({
                "type": "final",
                "answer": _try_parse_json(final_content),
            })

    return steps