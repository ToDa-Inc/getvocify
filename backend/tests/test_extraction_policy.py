from app.services.extraction_policy import (
    FILL_POLICY_LABELS,
    annotate_schema_fill_policies,
    apply_fill_policies,
    classify_fill_policy,
    fill_policy_instruction,
)
from app.services.extraction import (
    apply_enumeration_patch,
    build_extraction_prompt,
    drop_unspoken_numbers,
    number_was_spoken,
    pending_enumeration_specs,
    _normalize_raw_extraction,
)
from app.services.hubspot.types import CRMSchema, HubSpotProperty


def test_identity_and_strategy_and_research_policies():
    assert classify_fill_policy({"name": "firstname", "label": "First name"}) == "identity"
    assert classify_fill_policy({"name": "email", "label": "Email"}) == "identity"
    assert classify_fill_policy({"name": "call_angle", "label": "Call angle", "description": "pre-call talk track"}) == "strategy"
    assert classify_fill_policy({"name": "sales_motion", "label": "Sales motion", "description": "ICP fit"}) == "research"
    assert classify_fill_policy({"name": "description", "label": "Description"}) == "call_note"
    assert classify_fill_policy({"name": "amount", "label": "Amount"}) == "explicit"
    assert classify_fill_policy({"name": "vocify_context_status", "label": "Vocify Context Status"}) == "strategy"


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


def test_research_and_explicit_instructions_require_enum_mapping():
    research = fill_policy_instruction("research")
    explicit = fill_policy_instruction("explicit")
    assert "closest allowed option" in research
    assert "CURRENT VALUE is set" in research
    assert "ICP cutoffs" in research
    assert "closest allowed option" in explicit


def test_hubspot_call_prompt_fills_answered_discovery_fields():
    prompt = build_extraction_prompt(
        "Hola",
        field_specs=[
            {
                "name": "vocify_sales_motion",
                "label": "Vocify Sales Motion",
                "type": "enumeration",
                "object_type": "contacts",
                "options": [{"value": "partner_channel", "label": "Partner Channel"}],
            }
        ],
        source_context="hubspot_call",
    )
    assert "closest allowed option" in prompt
    assert "MUST set it" in prompt
    assert "only if explicitly stated" not in prompt


def test_drop_unspoken_numbers_keeps_said_headcount_only():
    specs = [
        {"name": "vocify_num_sales_reps", "type": "number", "object_type": "deals"},
        {"name": "vocify_contacts_per_day", "type": "number", "object_type": "deals"},
    ]
    transcript = "Hay 5 o 6 directores y 9 personas en Barcelona."
    out = drop_unspoken_numbers(
        {"vocify_num_sales_reps": 10, "vocify_contacts_per_day": 5},
        transcript,
        specs,
    )
    assert out["vocify_num_sales_reps"] is None
    assert out["vocify_contacts_per_day"] == 5
    assert number_was_spoken(6, "cinco o seis directores") is True
    assert number_was_spoken(7, "cinco o seis directores") is False


def test_pending_enumerations_skip_filled_strategy_and_existing():
    specs = [
        {
            "name": "vocify_sales_motion",
            "type": "enumeration",
            "object_type": "contacts",
            "options": [{"value": "partner_channel", "label": "Partner Channel"}],
        },
        {
            "name": "vocify_call_angle",
            "type": "enumeration",
            "object_type": "contacts",
            "label": "Call angle",
            "description": "pre-call talk track",
        },
        {
            "name": "vocify_crm_situation",
            "type": "enumeration",
            "object_type": "deals",
        },
    ]
    extracted = {
        "contact_properties": {"vocify_sales_motion": None},
        "vocify_crm_situation": "have_crm_not_filled",
    }
    pending = pending_enumeration_specs(
        extracted,
        specs,
        existing_values={"contacts": {"vocify_sales_motion": None}},
    )
    names = {s["name"] for s in pending}
    assert names == {"vocify_sales_motion"}
    patched = apply_enumeration_patch(
        extracted,
        {"contact_properties": {"vocify_sales_motion": "partner_channel"}},
        pending,
    )
    assert patched["contact_properties"]["vocify_sales_motion"] == "partner_channel"
    dotted = apply_enumeration_patch(
        {"contact_properties": {}},
        {"contacts.vocify_sales_motion": "partner_channel"},
        pending,
    )
    assert dotted["contact_properties"]["vocify_sales_motion"] == "partner_channel"


def test_normalize_maps_enum_labels_to_values():
    specs = [
        {
            "name": "vocify_sales_motion",
            "type": "enumeration",
            "object_type": "contacts",
            "options": [{"value": "partner_channel", "label": "Partner Channel"}],
        }
    ]
    out = _normalize_raw_extraction(
        {"contact_properties": {"vocify_sales_motion": "Partner Channel"}},
        specs,
    )
    assert out["contact_properties"]["vocify_sales_motion"] == "partner_channel"


def test_drops_current_value_echo_and_unknown_enum():
    specs = [
        {"name": "dealstage", "object_type": "deals", "type": "enumeration"},
        {
            "name": "vocify_sales_motion",
            "object_type": "contacts",
            "type": "enumeration",
            "options": [{"value": "partner_channel", "label": "Partner Channel"}],
        },
    ]
    out = apply_fill_policies(
        {
            "dealstage": "5022848247",
            "contact_properties": {"vocify_sales_motion": "unknown"},
        },
        specs,
        existing_values={
            "deals": {"dealstage": "5022848247"},
            "contacts": {},
        },
    )
    assert out.get("dealstage") is None
    assert out["contact_properties"].get("vocify_sales_motion") is None
