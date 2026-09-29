"""T7: the catalog, the rule schema, role visibility and the flags."""

from __future__ import annotations

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-playbooks-32b+")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-playbooks-32b+")

import pytest

from app.config import settings
from app.services.feature_flags import CLIENT_FLAGS, PLAYBOOK_V2_FLAGS
from app.services.playbooks import catalog
from app.services.playbooks.motion import flow_for_motion, goal_for, visible_to_role
from app.services.playbooks.structured import normalize_steps


def test_the_catalog_has_the_five_types_in_order():
    assert catalog.CATALOG_KEYS == ("discovery", "inbound", "ae_discovery", "closing", "negotiation")
    types = {entry["key"]: entry for entry in catalog.catalog_types()}
    assert {key: entry["role"] for key, entry in types.items()} == {
        "discovery": "sdr", "inbound": "sdr", "ae_discovery": "ae", "closing": "ae", "negotiation": "ae",
    }
    assert types["discovery"]["label"] == {"es": "Llamada en frío", "en": "Cold call"}
    assert types["inbound"]["label"] == {"es": "Lead inbound", "en": "Inbound lead"}
    assert types["closing"]["label"] == {"es": "Demo y cierre", "en": "Demo and close"}
    assert types["negotiation"]["label"] == {"es": "Propuesta y negociación", "en": "Proposal and negotiation"}
    assert {key: entry["goal"] for key, entry in types.items()} == {
        "discovery": "meeting_booked",
        "inbound": "meeting_booked",
        "ae_discovery": "demo_booked",
        "closing": "proposal_and_close",
        "negotiation": "close_date",
    }


def test_default_rules():
    assert catalog.default_applies_to("discovery") == {"role": "sdr", "channels": ["call"], "contact": "any", "deal_stages": []}
    assert catalog.default_applies_to("inbound") == {"role": "sdr", "channels": ["call"], "contact": "inbound", "deal_stages": []}
    assert catalog.default_applies_to("ae_discovery") == {
        "role": "ae", "channels": ["meeting", "visit", "call"], "contact": "new", "deal_stages": [],
    }
    assert catalog.default_applies_to("closing") == {"role": "ae", "channels": ["meeting", "visit"], "contact": "any", "deal_stages": []}
    assert catalog.default_applies_to("negotiation") == {
        "role": "ae", "channels": ["meeting", "visit", "call"], "contact": "any", "deal_stages": [],
    }
    assert catalog.default_applies_to("renewal") is None


def test_a_default_rule_is_a_copy():
    rule = catalog.default_applies_to("discovery")
    rule["channels"].append("meeting")
    assert catalog.default_applies_to("discovery")["channels"] == ["call"]


@pytest.mark.parametrize("lang", ["es", "en"])
@pytest.mark.parametrize("key", catalog.CATALOG_KEYS)
def test_every_template_is_valid_short_and_observable(key, lang):
    steps = catalog.template_steps(key, lang)
    assert 4 <= len(steps) <= 5
    # The same shape the editor and C04 use: the shared validator accepts it as is.
    normalized = normalize_steps(steps)
    assert [step["step_id"] for step in normalized] == [step["step_id"] for step in steps]
    for step in steps:
        assert set(step) == {"step_id", "label", "criterion"}
        assert len(step["label"].split()) <= 5
        assert 10 < len(step["criterion"]) <= 120


def test_the_endpoint_payload_carries_both_languages():
    for entry in catalog.catalog_types():
        assert set(entry) == {"key", "role", "goal", "applies_to", "label", "template"}
        assert set(entry["template"]) == {"es", "en"}
        assert [s["step_id"] for s in entry["template"]["es"]] == [s["step_id"] for s in entry["template"]["en"]]


def test_validate_applies_to_fills_the_optional_fields():
    assert catalog.validate_applies_to({"role": "ae"}) == {"role": "ae", "channels": [], "contact": "any", "deal_stages": []}
    rule = catalog.validate_applies_to(
        {"role": "sdr", "channels": ["visit", "call", "call"], "contact": "contacted", "deal_stages": [12, "won", "won"]}
    )
    assert rule == {"role": "sdr", "channels": ["visit", "call"], "contact": "contacted", "deal_stages": ["12", "won"]}
    # A default rule is already in its stored shape.
    for key in catalog.CATALOG_KEYS:
        assert catalog.validate_applies_to(catalog.default_applies_to(key)) == catalog.default_applies_to(key)


@pytest.mark.parametrize(
    "raw",
    [
        None,
        {},
        [],
        "sdr",
        {"role": "boss"},
        {"role": "ae", "channels": ["sms"]},
        {"role": "ae", "channels": "call"},
        {"role": "ae", "contact": "maybe"},
        {"role": "ae", "deal_stages": "won"},
        {"role": "ae", "deal_stages": [""]},
        {"role": "ae", "deal_stages": [None]},
        {"role": "ae", "deal_stages": [True]},
        {"role": "ae", "deal_stages": [str(n) for n in range(51)]},
        {"role": "ae", "surprise": 1},
    ],
)
def test_validate_applies_to_rejects_what_is_not_in_the_schema(raw):
    with pytest.raises(catalog.RuleError) as exc:
        catalog.validate_applies_to(raw)
    assert exc.value.code == "bad_rule"


def test_effective_rule_prefers_a_valid_stored_rule():
    stored = {"role": "sdr", "channels": ["meeting"], "contact": "any", "deal_stages": []}
    assert catalog.effective_applies_to("closing", stored) == stored
    assert catalog.effective_applies_to("closing", {"role": "nope"}) == catalog.default_applies_to("closing")
    assert catalog.effective_applies_to("closing", None) == catalog.default_applies_to("closing")
    assert catalog.effective_applies_to("renewal", None) is None
    assert catalog.effective_applies_to("renewal", stored) == stored


def test_flow_and_goal_cover_the_new_types():
    assert flow_for_motion("inbound") == "sdr"
    assert flow_for_motion("ae_discovery") == "ae"
    assert flow_for_motion("negotiation") == "ae"
    assert flow_for_motion("discovery") == "sdr"
    assert flow_for_motion("closing") == "ae"
    assert flow_for_motion("qualification") is None
    assert goal_for("inbound") == "meeting_booked"


def test_visibility_is_driven_by_the_types_role():
    for key in ("discovery", "inbound"):
        assert visible_to_role(key, "sdr") is True
        assert visible_to_role(key, "ae") is False
    for key in ("ae_discovery", "closing", "negotiation"):
        assert visible_to_role(key, "sdr") is False
        assert visible_to_role(key, "ae") is True
    for role in ("general", None, ""):
        for key in catalog.CATALOG_KEYS:
            assert visible_to_role(key, role) is True


def test_a_custom_type_is_visible_by_the_role_of_its_rule():
    ae_only = {"role": "ae", "channels": [], "contact": "any", "deal_stages": []}
    any_role = {"role": "any", "channels": ["call"], "contact": "any", "deal_stages": []}
    assert visible_to_role("renewal", "sdr", ae_only) is False
    assert visible_to_role("renewal", "ae", ae_only) is True
    assert visible_to_role("renewal", "sdr", any_role) is True
    assert visible_to_role("renewal", "ae", any_role) is True
    # Legacy custom type (no rule) and qualification stay visible to everybody.
    assert visible_to_role("renewal", "sdr") is True
    assert visible_to_role("qualification", "ae", None) is True


def test_both_flags_exist_off_by_default_and_reach_the_client():
    assert PLAYBOOK_V2_FLAGS == ("PLAYBOOK_V2_ENABLED", "PLAYBOOK_ROUTING_ENABLED")
    for flag in PLAYBOOK_V2_FLAGS:
        assert flag in CLIENT_FLAGS
        assert getattr(settings, flag) is False
