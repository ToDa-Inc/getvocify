"""Types by channel wired into capture, the call reading, the Interna tag and the CRM re-check."""

from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from app.services import captures
from app.services import memo_extraction_hooks as hooks
from app.services.playbooks import channel_types as ct
from app.services.playbooks import routing
from app.services.playbooks import type_classifier as tc

CALL = {"role": "any", "channels": ["call"], "contact": "any", "deal_stages": []}
MEETING = {"role": "any", "channels": ["meeting"], "contact": "any", "deal_stages": []}
INBOUND = {"role": "any", "channels": ["call"], "contact": "inbound", "deal_stages": []}
TYPES = {
    "cold": {"status": "published", "label": "Llamada en frío", "applies_to": CALL},
    "inbound_lead": {"status": "missing", "label": "Lead inbound", "applies_to": INBOUND},
    "demo": {"status": "draft", "label": "Demo", "applies_to": MEETING},
}


def _flag(on=True, types=TYPES, live="v1"):
    stack = ExitStack()
    stack.enter_context(patch.object(ct, "enabled", return_value=on))
    stack.enter_context(patch.object(ct, "_types", return_value=types))
    stack.enter_context(patch.object(ct, "live_version_id", side_effect=lambda _s, _c, key: live if key == "cold" else None))
    stack.enter_context(patch.object(ct, "live_snapshots", return_value=[]))
    return stack


def _memo(**fields):
    return {"id": "m1", "company_id": "c1", "interaction_kind": "call", "sales_motion_key": None, "pipeline_meta": {}, **fields}


def _write(supabase):
    """The row written by update(...), or None."""
    update = supabase.table.return_value.update
    return update.call_args.args[0] if update.called else None


# --- capture -----------------------------------------------------------------------------------

def test_a_meeting_is_pinned_to_its_only_type_without_a_playbook():
    with _flag():
        fields = captures.playbook_fields_for_capture(MagicMock(), "c1", interaction_kind="meeting", sales_role="sdr")
    assert fields["sales_motion_key"] == "demo" and fields["playbook_version_id"] is None
    assert fields["pipeline_meta"]["playbook_pin"]["source"] == "single"


def test_a_call_with_several_types_starts_with_none_and_never_by_role():
    with _flag(), patch.object(ct, "build_context", return_value={"contact": None, "inbound": None, "deal_stage": None}):
        assert captures.playbook_fields_for_capture(MagicMock(), "c1", interaction_kind="call", sales_role="ae",
                                                    default_when_unspecified=True) == {}


def test_a_type_the_capture_names_is_kept():
    with _flag(), patch.object(captures, "live_version_id", return_value="v1"):
        fields = captures.playbook_fields_for_capture(MagicMock(), "c1", sales_motion_key="cold", interaction_kind="call")
    assert fields["sales_motion_key"] == "cold"


# --- the call reading ---------------------------------------------------------------------------

def test_the_reading_is_offered_the_channels_types_and_internal():
    with _flag():
        offered = tc.reading_playbooks("c1", kind="call", supabase=MagicMock())
    assert set(offered) == {"cold", "inbound_lead", "internal"}
    assert offered["inbound_lead"].startswith("Lead inbound.")
    with _flag():
        assert tc.reading_playbooks("c1", kind="voice_note", supabase=MagicMock()) is None


def _read(memo, key):
    supabase = MagicMock()
    supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [memo]
    with _flag():
        tc.apply_reading_type(supabase, "m1", {"playbook": key})
    return supabase


def test_the_reading_decides_over_a_live_suggestion_and_the_write_skips_a_manual_pin():
    supabase = _read(_memo(sales_motion_key="cold", pipeline_meta={"playbook_pin": {"source": "live"}}), "inbound_lead")
    row = _write(supabase)
    assert row["sales_motion_key"] == "inbound_lead" and row["playbook_version_id"] is None
    assert row["pipeline_meta"]["playbook_pin"] == {"source": "reading", "changed_from": "cold"}
    supabase.table.return_value.update.return_value.eq.return_value.or_.assert_called_once_with(tc.NOT_MANUAL_FILTER)


def test_the_reading_never_moves_a_pick_or_a_crm_decision():
    for source in ("manual", "crm_rule"):
        assert _write(_read(_memo(sales_motion_key="cold", pipeline_meta={"playbook_pin": {"source": source}}), "inbound_lead")) is None


def test_the_channels_only_type_can_only_turn_out_internal():
    single = {"playbook_pin": {"source": "single"}}
    assert _write(_read(_memo(interaction_kind="meeting", sales_motion_key="demo", pipeline_meta=single), "cold")) is None
    row = _write(_read(_memo(interaction_kind="meeting", sales_motion_key="demo", pipeline_meta=single), "internal"))
    assert row["sales_motion_key"] == "internal"


def test_the_reading_cannot_pin_a_type_of_another_channel():
    assert _write(_read(_memo(interaction_kind="call"), "demo")) is None


# --- one Interna detector -------------------------------------------------------------------------

def test_extractions_internal_tag_waits_for_nothing_when_the_call_was_read():
    memo = _memo(sales_motion_key="cold", extraction={"call_reading": {"call_type": "follow_up"}})
    supabase = MagicMock()
    with _flag(), patch("app.services.feature_flags.is_enabled", return_value=True):
        assert hooks._tag_internal(supabase, memo, {"customerPresent": False}) is memo
    assert _write(supabase) is None


# --- the CRM re-check before C04 ------------------------------------------------------------------

def test_a_saved_crm_condition_known_after_capture_beats_the_reading():
    memo = _memo(sales_motion_key="cold", hubspot_contact_id="77", pipeline_meta={"playbook_pin": {"source": "reading"}})
    supabase = MagicMock()
    with _flag(), patch.object(ct, "build_context", return_value={"contact": None, "inbound": True, "deal_stage": None}):
        out = routing.repin_before_c04(supabase, memo)
    assert out["sales_motion_key"] == "inbound_lead"
    assert out["pipeline_meta"]["playbook_pin"] == {"source": "crm_rule", "repinned_from": "cold"}


def test_the_crm_re_check_leaves_a_pick_alone_and_never_reads_the_role():
    memo = _memo(sales_motion_key="cold", pipeline_meta={"playbook_pin": {"source": "manual"}})
    with _flag(), patch.object(ct, "build_context") as context:
        assert routing.repin_before_c04(MagicMock(), memo) is memo
    context.assert_not_called()
