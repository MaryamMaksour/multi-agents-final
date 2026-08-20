from enum import Enum


class ResponseSignal(str, Enum):
    """User-facing signals. Technical detail stays in the logs."""
    CHAT_SUCCESS = "chat_success"
    CHAT_FAILED = "chat_failed"
    INVALID_INPUT = "invalid_user_input"
    AGENT_NO_RESPONSE = "agent_returned_no_response"
    UNKNOWN_DOMAIN = "unknown_domain"
    SUB_AGENT_UNREACHABLE = "sub_agent_unreachable"
