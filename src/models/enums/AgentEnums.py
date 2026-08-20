from enum import Enum


class AgentKind(str, Enum):
    """What kind of agent this is - the axis that varies by *code*.

    A new kind means a new provider class under stores/agents/providers/.
    A new *domain* of an existing kind (another set of SQL tables) means
    only a new spec under stores/agents/specs/ - no new code.
    """
    SQL = "sql"
    SHEET = "sheet"       # planned: spreadsheet analysis over a temp table
    REMOTE = "remote"     # a sub-agent reached over HTTP


class AgentRole(str, Enum):
    ORCHESTRATOR = "orchestrator"
    SUB_AGENT = "sub_agent"


class DomainKey(str, Enum):
    HR = "hr"
    CRM = "crm"
