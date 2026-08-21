"""One prompt body, many domains."""
from stores.agents.prompts import TemplateParser
from stores.agents.specs import get_spec


def _prompt_for(domain: str) -> str:
    spec = get_spec(domain)
    return TemplateParser().get("sql_agent", "system_prompt", {
        "domain_label": spec.description,
        "relations": spec.relations,
        "normalizations": spec.normalizations,
        "defaults": spec.defaults,
    })


def test_domain_fragments_are_substituted():
    hr = _prompt_for("hr")
    assert get_spec("hr").description in hr
    assert "hos_employee.id" in hr
    assert "$relations" not in hr and "$defaults" not in hr


def test_sql_placeholders_survive_templating():
    """The prompt is full of $1, $2 - substitution must not eat them."""
    assert "$1, $2" in _prompt_for("hr")


def test_two_domains_share_one_body_and_differ_only_in_data():
    hr, crm = _prompt_for("hr"), _prompt_for("crm")
    assert "customerrequesttrackers" in crm and "customerrequesttrackers" not in hr
    assert "hos_employee" in hr and "hos_employee" not in crm
    # The shared instructions really are shared, not two near-copies.
    shared = "Never write LIMIT or OFFSET"
    assert shared in hr and shared in crm


def test_orchestrator_catalog_is_generated_from_the_registry():
    from stores.agents.specs import AGENT_REGISTRY

    catalog = "\n".join(f"  - ask_{key}_agent: x" for key in AGENT_REGISTRY)
    prompt = TemplateParser().get("orchestrator", "system_prompt", {"agent_catalog": catalog})

    for key in AGENT_REGISTRY:
        assert f"ask_{key}_agent" in prompt
