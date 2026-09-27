"""F16: queue/Hoy exit by CRM state. Edge cases E1–E18."""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-hoy-crm-state-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-hoy-crm-state-32")

from app.services.feature_flags import clear_cache
from app.services.hoy.crm_state import (
    FLAG,
    QueueStates,
    confirmed_state_from_extraction,
    contact_exit_states,
    exit_reason,
    load_queue_states,
    pick_deal_state,
    queue_states_enabled,
)
from app.services.hoy.memo_facts import apply_memo_facts, memo_facts_by_contact
from app.services.hoy.priority import rank_candidates
from app.services.hoy.signals import Commitment, Touch, signals_for_contact
from datetime import datetime, timedelta, timezone

NOW = datetime(2026, 9, 22, 10, 0, tzinfo=timezone.utc)
DAY_END = datetime(2026, 9, 22, 21, 59, tzinfo=timezone.utc)
COMPANY = "co-1"

BOOKED = QueueStates(source="deal_stage", booked=("appointmentscheduled",), ended=("closedlost",))
LEAD = QueueStates(source="lead_status", booked=("CONNECTED",), ended=("UNQUALIFIED",))


class _Flags:
    def __init__(self, rows):
        self.rows = rows

    def table(self, name):
        assert name == "company_feature_flags"
        return self

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a):
        return self

    def execute(self):
        return SimpleNamespace(data=self.rows)


def _flags(*pairs):
    clear_cache()
    return _Flags([{"company_id": COMPANY, "flag": f, "enabled": on} for f, on in pairs])


def test_e1_flag_off_keeps_meeting_agreed_exit():
    """E1: flag off → current behaviour (meeting_agreed removes)."""
    assert queue_states_enabled(_flags(), COMPANY) is False
    ranked = rank_candidates(
        [{"connection_id": "c", "contact_id": "1", "coverage": "complete", "meeting_agreed": True}],
        NOW,
        states=None,
    )
    assert ranked == []


def test_e2_flag_on_empty_states_nobody_exits_even_with_meeting_agreed():
    """E2: flag on, no states marked → nobody exits by state; meeting_agreed ignored."""
    empty = QueueStates(source="deal_stage", booked=(), ended=())
    assert exit_reason("appointmentscheduled", empty) is None
    ranked = rank_candidates(
        [{
            "connection_id": "c", "contact_id": "1", "coverage": "complete",
            "meeting_agreed": True, "crm_state": "qualifiedtobuy", "last_call_at": "2026-09-01T00:00:00Z",
        }],
        NOW,
        states=empty,
    )
    assert [r["contact_id"] for r in ranked] == ["1"]


def test_e3_ai_meeting_other_state_stays_in_queue():
    """E3: AI detects meeting but rep confirms a non-exit state → stays."""
    ranked = rank_candidates(
        [{
            "connection_id": "c", "contact_id": "1", "coverage": "complete",
            "meeting_agreed": True, "crm_state": "qualifiedtobuy", "last_call_at": "2026-09-01T00:00:00Z",
        }],
        NOW,
        states=BOOKED,
    )
    assert [r["contact_id"] for r in ranked] == ["1"]


def test_e4_booked_state_exits_queue():
    """E4: confirmed booked state → out of queue."""
    assert exit_reason("appointmentscheduled", BOOKED) == "booked"
    ranked = rank_candidates(
        [{
            "connection_id": "c", "contact_id": "1", "coverage": "complete",
            "crm_state": "appointmentscheduled", "last_call_at": "2026-09-01T00:00:00Z",
        }],
        NOW,
        states=BOOKED,
    )
    assert ranked == []


def test_e5_ended_state_exits_queue():
    """E5: confirmed ended state → out of queue."""
    assert exit_reason("closedlost", BOOKED) == "ended"
    ranked = rank_candidates(
        [{
            "connection_id": "c", "contact_id": "1", "coverage": "complete",
            "crm_state": "closedlost", "last_call_at": "2026-09-01T00:00:00Z",
        }],
        NOW,
        states=BOOKED,
    )
    assert ranked == []


def test_e6_e7_crm_state_from_cache_drives_membership():
    """E6/E7: next CRM read updates crm_state; non-exit state returns to queue."""
    exited = contact_exit_states(
        [{"contact_id": "1", "payload": {"crm_state": "appointmentscheduled"}}],
        BOOKED,
    )
    assert exited == {"1"}
    back = contact_exit_states(
        [{"contact_id": "1", "payload": {"crm_state": "qualifiedtobuy"}}],
        BOOKED,
    )
    assert back == set()


def test_e8_pick_deal_most_recent_then_greater_id():
    """E8: most recently modified deal; tie → greater id."""
    assert pick_deal_state([
        {"id": "1", "dealstage": "a", "updated_at": "2026-09-20T10:00:00Z"},
        {"id": "2", "dealstage": "b", "updated_at": "2026-09-21T10:00:00Z"},
    ]) == "b"
    assert pick_deal_state([
        {"id": "1", "dealstage": "a", "updated_at": "2026-09-21T10:00:00Z"},
        {"id": "9", "dealstage": "b", "updated_at": "2026-09-21T10:00:00Z"},
    ]) == "b"


def test_e9_no_deal_no_state_stays_in_queue():
    """E9: no deal → no state → stays in queue."""
    assert pick_deal_state([]) is None
    ranked = rank_candidates(
        [{
            "connection_id": "c", "contact_id": "1", "coverage": "complete",
            "last_call_at": "2026-09-01T00:00:00Z",
        }],
        NOW,
        states=BOOKED,
    )
    assert [r["contact_id"] for r in ranked] == ["1"]


def test_e10_lead_mode_without_options_never_matches():
    """E10: lead mode with empty exit lists → nobody exits."""
    empty_lead = QueueStates(source="lead_status", booked=(), ended=())
    assert exit_reason("CONNECTED", empty_lead) is None


def test_e11_missing_crm_state_key_does_not_exit():
    """E11: failed read leaves no crm_state key → previous kept; absent key does not exit."""
    assert exit_reason(None, BOOKED) is None
    assert contact_exit_states([{"contact_id": "1", "payload": {}}], BOOKED) == set()


def test_e12_unattended_extraction_has_no_confirmed_state_for_lead():
    """E12: unattended path strips lead status; confirmed_state sees nothing to write."""
    from app.services.llm.lead_status import strip_lead_status_for_unattended_sync

    raw = {"raw_extraction": {"contact_properties": {"hs_lead_status": "CONNECTED"}}}
    stripped = strip_lead_status_for_unattended_sync(raw)
    assert confirmed_state_from_extraction(stripped, "lead_status", "hubspot") is None


def test_e13_confirmed_state_only_from_reviewed_extraction():
    """E13 companion: confirmed state is read from reviewed extraction; empty means no cache write."""
    assert confirmed_state_from_extraction({}, "deal_stage", "hubspot") is None
    assert confirmed_state_from_extraction(
        {"dealStage": "appointmentscheduled", "raw_extraction": {"dealstage": "appointmentscheduled"}},
        "deal_stage",
        "hubspot",
    ) == "appointmentscheduled"


def test_e14_pipedrive_won_lost():
    """E14: Pipedrive won/lost → status:won / status:lost."""
    assert pick_deal_state([{"id": "1", "status": "won", "stage_id": 3, "update_time": "2026-09-21T10:00:00Z"}], provider="pipedrive") == "status:won"
    assert pick_deal_state([{"id": "1", "status": "lost", "stage_id": 3, "update_time": "2026-09-21T10:00:00Z"}], provider="pipedrive") == "status:lost"
    assert pick_deal_state([{"id": "1", "status": "open", "stage_id": 7, "update_time": "2026-09-21T10:00:00Z"}], provider="pipedrive") == "7"


def test_e15_pipedrive_forces_deal_stage_source():
    """E15: Pipedrive lead_status request is stored as deal_stage."""
    from app.models.crm_config import CRMConfigurationRequest
    from app.services.crm_config import _normalize_queue_states

    req = CRMConfigurationRequest(
        default_pipeline_id="1",
        default_pipeline_name="Sales",
        default_stage_id="1",
        default_stage_name="New",
        queue_state_source="lead_status",
        queue_booked_states=["3"],
    )
    assert _normalize_queue_states(req, provider="pipedrive")["queue_state_source"] == "deal_stage"


def test_e16_state_overlap_prefers_booked_list():
    """E16 companion: admin changes apply via loaded states; overlapping ids stay only in booked."""
    from app.models.crm_config import CRMConfigurationRequest
    from app.services.crm_config import _normalize_queue_states

    req = CRMConfigurationRequest(
        default_pipeline_id="1",
        default_pipeline_name="Sales",
        default_stage_id="1",
        default_stage_name="New",
        queue_booked_states=["a", "a", "b"],
        queue_ended_states=["b", "c"],
    )
    normalized = _normalize_queue_states(req, provider="hubspot")
    assert normalized["queue_booked_states"] == ["a", "b"]
    assert normalized["queue_ended_states"] == ["c"]


def test_e17_unknown_configured_state_never_matches():
    """E17: configured id no longer in CRM never matches a live state."""
    states = QueueStates(source="deal_stage", booked=("gone",), ended=())
    assert exit_reason("appointmentscheduled", states) is None


def test_e18_deal_closed_does_not_suppress_when_flag_ignores_it():
    """E18: with flag, inferred deal_closed does not suppress Hoy signals."""
    touch = Touch(
        memo_id="m1",
        contact_id="1",
        deal_id=None,
        at=NOW - timedelta(days=12),
        interest="high",
        objections=(),
        commitments=(),
        deal_closed=True,
    )
    assert signals_for_contact([touch], now=NOW, day_end=DAY_END) == []
    kept = signals_for_contact([touch], now=NOW, day_end=DAY_END, ignore_deal_closed=True)
    assert [s.type for s in kept] == ["going_cold"]


def test_flag_requires_deal_stage_confirm():
    assert queue_states_enabled(_flags((FLAG, True)), COMPANY) is False
    assert queue_states_enabled(
        _flags((FLAG, True), ("DEAL_STAGE_CONFIRM_ENABLED", True)),
        COMPANY,
    ) is True


def test_memo_facts_skip_meeting_agreed_when_asked():
    memos = [{
        "id": "m1",
        "created_at": "2026-09-21T10:00:00Z",
        "hubspot_contact_id": "42",
        "extraction": {"intelligence": {"meeting": {"agreed": True}}},
    }]
    assert memo_facts_by_contact(memos, now=NOW)["42"].get("meeting_agreed") is True
    facts = memo_facts_by_contact(memos, now=NOW, ignore_meeting_agreed=True)
    assert "meeting_agreed" not in facts["42"]


def test_lead_confirmed_state_from_contact_properties():
    assert confirmed_state_from_extraction(
        {"raw_extraction": {"contact_properties": {"hs_lead_status": "CONNECTED"}}},
        "lead_status",
        "hubspot",
    ) == "CONNECTED"


def test_load_queue_states_none_when_flag_off():
    clear_cache()
    assert load_queue_states(_flags(), COMPANY) is None
