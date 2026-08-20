"""HR / internal organization domain."""
from models.enums import AgentKind

from .DomainSpec import DomainSpec

# NOTE ON SCOPE: the previous HR prompt described the Brokers table and
# the orchestrator's HR tool advertised brokers, but `brokers` was never
# in this domain's allowlist and the HR Postgres role was never granted
# SELECT on it - so every broker question failed. The table list here is
# the one that is actually granted; the broker section has been dropped
# from the prompt to match. Widening the domain is a data-access
# decision, so it is left to be made deliberately: add "brokers" below
# *and* add the matching GRANT in
# docker/postgres/least_privilege_roles.sql.
spec = DomainSpec(
    key="hr",
    kind=AgentKind.SQL,
    title="HR Agent",
    description="Internal organization data: employees, management hierarchy, teams",
    tool_description=(
        "Internal organization and HR data: employees, heads of sales, directors, "
        "teams, and sales agents - who works here, their role, department, team, "
        "reporting line and employment status."
    ),
    history_table="history_hr",
    tables=[
        "employees",
        "directors_employees",
        "hos_employee",
        "teams",
        "agents_employee",
    ],
    table_notes={
        "employees": "All employees: name, role, position, department, section, manager, status.",
        "directors_employees": "Directors joined with the head of sales above them.",
        "hos_employee": "Heads of sales.",
        "teams": "Teams, each owned by a director.",
        "agents_employee": "Sales agents, each belonging to a team.",
    },
    relations="""RELATIONS
The organization is a chain: HOS -> Director -> Team -> Agent.
  directors_employees.hosid  -> hos_employee.id
  teams.directorid           -> directors_employees.id
  agents_employee.teamid     -> teams.id
  employees.reportingmanagerid -> employees.id   (self-join for line management)
agents_employee also carries a foreign key to employees.id; it holds only
the agent's SAP number and team, so join to employees for personal details.
Only these relationships exist. Do not invent a join.""",
    normalizations="""VALUES
  status        'Active' or 'Inactive'
  portalstatus  'true' or 'false'
  role          a numeric code, not a title
  position      free text
  department    one of: EV, EV Sales, EV Sales Saudi
  section       the team name
  nationality   a country name
  stage, type   '1' | '2' | '3' | '4'
Call get_distinct_values when unsure what a column really contains.""",
    defaults="""DEFAULTS
Filter to status = 'Active' unless the user asks for former or inactive
people, or asks about everyone.""",
)
