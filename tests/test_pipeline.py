"""Trace versus shape.

The whole point of producing two views is that one may be replayed into
a future prompt and the other may not. A change that lets result rows
leak into the shape is exactly the regression this guards.
"""
import json

from langchain_core.messages import AIMessage, ToolMessage

from utils.pipeline import extract_pipeline


def _run():
    return [
        AIMessage(content="", tool_calls=[{
            "name": "execute_sql",
            "args": {"query": "SELECT id, salary FROM employees", "params": [], "session_id": "s"},
            "id": "c1", "type": "tool_call",
        }]),
        ToolMessage(
            tool_call_id="c1", name="execute_sql",
            content=json.dumps({"rows": [{"id": 1, "salary": 90000}], "total": 1}),
        ),
        AIMessage(content=json.dumps({"data": [{"id": 1, "salary": 90000}]})),
    ]


def test_trace_keeps_everything_for_the_audit_record():
    trace, _shape = extract_pipeline(_run())
    tool_step = trace[0]

    assert tool_step["name"] == "execute_sql"
    assert tool_step["result"]["rows"][0]["salary"] == 90000


def test_shape_carries_the_reasoning_and_none_of_the_data():
    _trace, shape = extract_pipeline(_run())
    serialized = json.dumps(shape)

    # The SQL and the tool sequence are what teach a later prompt.
    assert shape[0]["name"] == "execute_sql"
    assert "SELECT id, salary FROM employees" in serialized

    # The rows those calls returned are not.
    assert "90000" not in serialized
    assert all("result" not in step for step in shape)
    assert shape[-1] == {"type": "final"}


def test_request_identifiers_are_stripped_from_examples():
    _trace, shape = extract_pipeline(_run())
    assert "session_id" not in shape[0]["args"]


def test_errors_are_kept_in_the_shape():
    """A failed turn is only useful as a counter-example if the reason survives."""
    messages = [
        AIMessage(content="", tool_calls=[
            {"name": "execute_sql", "args": {"query": "SELECT * FROM employees"}, "id": "c1", "type": "tool_call"}
        ]),
        ToolMessage(tool_call_id="c1", name="execute_sql",
                    content=json.dumps({"error": "select * is not allowed"})),
        AIMessage(content="{}"),
    ]
    _trace, shape = extract_pipeline(messages)
    assert shape[0]["error"] == "select * is not allowed"
