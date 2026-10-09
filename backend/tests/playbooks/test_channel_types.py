"""Types by channel (TYPE_BY_CHANNEL_ENABLED): which types a recording can be, and who may move its pin."""

from unittest.mock import patch

from app.services.playbooks import channel_types as ct

CALL_ONLY = {"role": "any", "channels": ["call"], "contact": "any", "deal_stages": []}
MEETING_ONLY = {"role": "any", "channels": ["meeting"], "contact": "any", "deal_stages": []}
BOTH = {"role": "any", "channels": ["call", "meeting"], "contact": "any", "deal_stages": []}


def _row(status="published", applies_to=None, label=None, recognize=None):
    return {"status": status, "label": label, "applies_to": applies_to, "recognize": recognize}


# --- a type's channels --------------------------------------------------------------------------

def test_a_type_belongs_to_the_channels_its_rule_names():
    assert ct.type_channels("cold", CALL_ONLY) == {"call"}
    assert ct.type_channels("demo", BOTH) == {"call", "meeting"}


def test_a_type_with_no_channel_or_no_rule_belongs_to_both():
    assert ct.type_channels("legacy_custom", None) == {"call", "meeting"}
    assert ct.type_channels("x", {"role": "any", "channels": [], "contact": "any", "deal_stages": []}) == {"call", "meeting"}


def test_a_catalog_type_without_a_stored_rule_takes_the_catalog_channels():
    assert ct.type_channels("discovery", None) == {"call"}
    assert ct.type_channels("closing", None) == {"meeting", "visit"}


def test_the_stored_role_is_ignored():
    sdr_call = {"role": "sdr", "channels": ["call"], "contact": "any", "deal_stages": []}
    assert ct.type_channels("cold", sdr_call) == {"call"}


# --- candidates --------------------------------------------------------------------------------

TYPES = {
    "cold": _row(applies_to=CALL_ONLY),
    "inbound_lead": _row(status="missing", applies_to=CALL_ONLY),
    "demo": _row(status="draft", applies_to=MEETING_ONLY),
    "followup": _row(applies_to=BOTH),
    "old": _row(status="paused", applies_to=CALL_ONLY),
    "internal": _row(),
}


def test_candidates_are_the_channels_types_with_or_without_a_playbook():
    assert ct.candidates(TYPES, "call") == ["cold", "followup", "inbound_lead"]
    assert ct.candidates(TYPES, "meeting") == ["demo", "followup"]


def test_a_paused_type_and_internal_are_never_candidates():
    assert "old" not in ct.candidates(TYPES, "call")
    assert "internal" not in ct.candidates(TYPES, "call")


def test_voice_notes_visits_and_unknown_channels_have_no_candidates():
    for kind in ("voice_note", "visit", None, ""):
        assert ct.candidates(TYPES, kind) == []


# --- the CRM condition ---------------------------------------------------------------------------

def _rule(contact="any", stages=(), role="any", channels=("call",)):
    return {"role": role, "channels": list(channels), "contact": contact, "deal_stages": list(stages)}


def test_only_role_free_rules_with_a_crm_condition_decide():
    types = {
        "cold": _row(applies_to=_rule()),
        "inbound_lead": _row(applies_to=_rule(contact="inbound")),
        "sdr_new": _row(applies_to=_rule(contact="new", role="sdr")),
    }
    rules = ct.crm_rules(types, ["cold", "inbound_lead", "sdr_new"])
    assert [rule["key"] for rule in rules] == ["inbound_lead"]


def test_a_catalog_default_never_decides_by_crm():
    # inbound's catalog default has contact=inbound, but the company never saved it.
    assert ct.crm_rules({"inbound": _row(applies_to=None)}, ["inbound"]) == []


def test_the_crm_choice_is_the_one_rule_that_matches():
    rules = [
        {"key": "inbound_lead", "applies_to": _rule(contact="inbound")},
        {"key": "new_lead", "applies_to": _rule(contact="new")},
    ]
    assert ct.crm_choice(rules, "call", {"contact": "new", "inbound": True, "deal_stage": None}) is None
    assert ct.crm_choice(rules, "call", {"contact": "contacted", "inbound": True, "deal_stage": None}) == "inbound_lead"
    assert ct.crm_choice(rules, "call", {"contact": None, "inbound": None, "deal_stage": None}) is None


def test_the_most_specific_match_wins_and_a_tie_decides_nothing():
    rules = [
        {"key": "a", "applies_to": _rule(contact="contacted")},
        {"key": "b", "applies_to": _rule(contact="contacted", stages=["s1"])},
    ]
    context = {"contact": "contacted", "inbound": None, "deal_stage": "s1"}
    assert ct.crm_choice(rules, "call", context) == "b"
    tie = [{"key": "a", "applies_to": _rule(contact="new")}, {"key": "c", "applies_to": _rule(contact="new")}]
    assert ct.crm_choice(tie, "call", {"contact": "new", "inbound": None, "deal_stage": None}) is None


# --- who may move a pin ---------------------------------------------------------------------------

def test_a_manual_or_crm_pin_is_final():
    for source in ("manual", "crm_rule"):
        assert not ct.may_move({"playbook_pin": {"source": source}}, "cold")
        assert not ct.may_move({"playbook_pin": {"source": source}}, "internal")


def test_a_single_candidate_pin_only_moves_to_internal():
    meta = {"playbook_pin": {"source": "single"}}
    assert not ct.may_move(meta, "cold")
    assert ct.may_move(meta, "internal")


def test_live_reading_and_unpinned_memos_move():
    for meta in ({"playbook_pin": {"source": "live"}}, {"playbook_pin": {"source": "reading"}}, {}, None):
        assert ct.may_move(meta, "cold")


# --- the capture pin ------------------------------------------------------------------------------

def test_capture_pins_the_only_candidate():
    with patch.object(ct, "_types", return_value={"cold": _row(applies_to=CALL_ONLY), "demo": _row(applies_to=MEETING_ONLY)}):
        assert ct.resolve_at_capture(object(), "c1", kind="call") == ("cold", "single")


def test_capture_leaves_several_candidates_to_the_reading_without_a_crm_rule():
    types = {"cold": _row(applies_to=CALL_ONLY), "followup": _row(applies_to=BOTH)}
    with patch.object(ct, "_types", return_value=types):
        assert ct.resolve_at_capture(object(), "c1", kind="call") == (None, None)


def test_capture_uses_a_crm_rule_when_one_decides():
    types = {"cold": _row(applies_to=CALL_ONLY), "inbound_lead": _row(applies_to=_rule(contact="inbound"))}
    with patch.object(ct, "_types", return_value=types), \
            patch.object(ct, "build_context", return_value={"contact": None, "inbound": True, "deal_stage": None}):
        assert ct.resolve_at_capture(object(), "c1", kind="call", contact_id="h1") == ("inbound_lead", "crm_rule")


def test_capture_with_no_candidates_or_a_failed_read_pins_nothing():
    with patch.object(ct, "_types", return_value={"demo": _row(applies_to=MEETING_ONLY)}):
        assert ct.resolve_at_capture(object(), "c1", kind="call") == (None, None)
    with patch.object(ct, "_types", side_effect=RuntimeError("db down")):
        assert ct.resolve_at_capture(object(), "c1", kind="call") == (None, None)


def test_pin_fields_carry_the_live_version_or_none():
    with patch.object(ct, "live_version_id", return_value="v1"):
        fields = ct.pin_fields(object(), "c1", "cold", "single")
    assert fields["sales_motion_key"] == "cold" and fields["playbook_version_id"] == "v1"
    assert fields["pipeline_meta"]["playbook_pin"]["source"] == "single"
    with patch.object(ct, "live_version_id", return_value=None):
        assert ct.pin_fields(object(), "c1", "inbound_lead", "single")["playbook_version_id"] is None
    assert ct.pin_fields(object(), "c1", "internal", "reading")["playbook_version_id"] is None


# --- what the AI is told about each candidate -----------------------------------------------------

def test_a_candidate_is_described_by_name_recognition_and_steps():
    types = {
        "cold": _row(label="Llamada en frío", recognize="First call to someone who never heard of us.", applies_to=CALL_ONLY),
        "inbound_lead": _row(status="missing", label="Lead inbound", applies_to=CALL_ONLY),
    }
    snapshots = [{"sales_motion_key": "cold", "steps": [{"label": "Abrir"}, {"label": "Cualificar"}]}]
    with patch.object(ct, "live_snapshots", return_value=snapshots):
        described = ct.describe(object(), "c1", types, ["cold", "inbound_lead"])
    assert described["cold"].startswith("Llamada en frío.")
    assert "never heard of us" in described["cold"] and "Abrir, Cualificar" in described["cold"]
    assert described["inbound_lead"] == "Lead inbound."
