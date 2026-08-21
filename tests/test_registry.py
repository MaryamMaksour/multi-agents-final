"""The registry is the contract between a domain and everything else."""
import pytest

from models.enums import AgentKind
from stores.agents.specs import AGENT_REGISTRY, get_spec, registered_domains


def test_hr_and_crm_are_registered():
    assert registered_domains() == ["crm", "hr"]


def test_domains_are_data_over_one_implementation():
    """Two domains, same kind - so they share code and differ only in values."""
    hr, crm = get_spec("hr"), get_spec("crm")
    assert hr.kind is crm.kind is AgentKind.SQL
    assert set(hr.tables).isdisjoint(crm.tables)
    assert hr.history_table != crm.history_table


@pytest.mark.parametrize("domain", ["hr", "crm"])
def test_every_declared_table_has_a_schema(domain):
    """A table in the allowlist with no schema is a runtime failure waiting."""
    from models import schema_registry

    for table in get_spec(domain).tables:
        assert schema_registry.table_exists(table), f"{domain}: no schema for {table}"
        assert schema_registry.columns_of(table), f"{domain}: {table} parsed to zero columns"


@pytest.mark.parametrize("domain", ["hr", "crm"])
def test_history_tables_are_valid_identifiers(domain):
    from models.BaseDataModel import BaseDataModel

    BaseDataModel.validate_table_name(get_spec(domain).history_table)


def test_domains_do_not_overlap():
    """Overlapping allowlists would blur the boundary the DB roles enforce."""
    seen = {}
    for key, spec in AGENT_REGISTRY.items():
        for table in spec.tables:
            assert table not in seen, f"{table} claimed by both {seen.get(table)} and {key}"
            seen[table] = key


def test_unknown_domain_fails_loudly():
    with pytest.raises(ValueError):
        get_spec("does_not_exist")
