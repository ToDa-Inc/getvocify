from app.services.extraction_policy import (
    FILL_POLICY_LABELS,
    annotate_schema_fill_policies,
    classify_fill_policy,
)
from app.services.hubspot.types import CRMSchema, HubSpotProperty


def test_identity_and_strategy_and_research_policies():
    assert classify_fill_policy({"name": "firstname", "label": "First name"}) == "identity"
    assert classify_fill_policy({"name": "email", "label": "Email"}) == "identity"
    assert classify_fill_policy({"name": "call_angle", "label": "Call angle", "description": "pre-call talk track"}) == "strategy"
    assert classify_fill_policy({"name": "sales_motion", "label": "Sales motion", "description": "ICP fit"}) == "research"
    assert classify_fill_policy({"name": "description", "label": "Description"}) == "call_note"
    assert classify_fill_policy({"name": "amount", "label": "Amount"}) == "explicit"


def test_annotate_schema_fill_policies_sets_policy_on_properties():
    schema = CRMSchema(
        object_type="contacts",
        properties=[
            HubSpotProperty(name="firstname", label="First name", type="string", description="Contact first name"),
            HubSpotProperty(name="phone", label="Phone", type="string"),
        ],
    )
    out = annotate_schema_fill_policies(schema)
    by_name = {p.name: p.fill_policy for p in out.properties}
    assert by_name["firstname"] == "identity"
    assert by_name["phone"] == "explicit"
    assert FILL_POLICY_LABELS["identity"] == "Keep existing"
