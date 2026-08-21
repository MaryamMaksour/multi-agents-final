from enum import Enum


class EventType(str, Enum):
    USER = "user"
    TOOL = "tool"
    SQL = "sql"
    ASSISTANT_FINAL = "assistant_final"
