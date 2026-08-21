"""CRM / external customer domain."""
from models.enums import AgentKind

from .DomainSpec import DomainSpec

spec = DomainSpec(
    key="crm",
    kind=AgentKind.SQL,
    title="CRM Agent",
    description="External customer data: customers, their deals and their requests",
    tool_description=(
        "External customer data: customers and prospects, the deals attached to "
        "them, and their request/enquiry history - who the customer is, their "
        "nationality, company, type, status, and what they asked for."
    ),
    history_table="history_crm",
    tables=[
        "customers",
        "customerrequesttrackers",
        "customers_deals",
    ],
    table_notes={
        "customers": "Customers and prospects: names (English and Arabic), nationality, company, type, status.",
        "customerrequesttrackers": "Requests and enquiries raised by customers.",
        "customers_deals": "Customers joined with the deals attached to them.",
    },
    relations="""RELATIONS
  customers -> customers_deals               (a customer's deals)
  customers -> customerrequesttrackers       (a customer's requests)
Only these relationships exist. Do not invent a join.

Customer names are stored in both English and Arabic (fullnameen,
fullnamear) and companies likewise (companynameen, companynamear). When
searching by name, search both and combine with OR - which language a
record was entered in is not predictable.""",
    normalizations="""VALUES
  customers.status            '0' | '1' | '2'
  customers.type              'Individual' or 'Corporate'
  customers.isfirsttimebuyer  'true' or 'false'
  customerrequesttrackers.isactive  'true' or 'false'
  customerrequesttrackers.lable     'Submitted' or 'Invited'
  customerrequesttrackers.status    '1' | '2'
Call get_distinct_values when unsure what a column really contains.""",
    defaults="""DEFAULTS
No status filter is applied unless the user asks for one.""",
)
