from datetime import datetime, timedelta, timezone

from app.services.hoy.materialize import (
    exclude_handoff_contacts,
    fresh_signals,
    never_contacted_signals,
    retracted_objection_ids,
)
from app.services.hoy.signals import Signal


NOW = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
DAY_END = datetime(2026, 9, 24, 21, 59, tzinfo=timezone.utc)


def test_a_stored_open_objection_becomes_one_signal_without_a_model():
    signals = fresh_signals(
        [{
            "id": "memo-1",
            "hubspot_contact_id": "42",
            "capture_started_at": "2026-09-20T10:00:00Z",
            "extraction": {
                "intelligence": {
                    "interest": "high",
                    "objections": [{"resolution": "open", "category": "price", "quote": "Está caro"}],
                }
            },
        }],
        now=NOW,
        day_end=DAY_END,
    )
    assert [signal.type for signal in signals] == ["objection_open"]
    assert signals[0].payload["category"] == "price"
    assert "caro" in signals[0].payload["quote"]


def _memo_with_empty_c04():
    return {
        "id": "memo-1",
        "hubspot_contact_id": "42",
        "capture_started_at": "2026-09-20T10:00:00Z",
        "extraction": {
            "objections": ["No es el mejor momento"],
            "intelligence": {"interest": "high", "objections": []},
        },
    }


def test_current_intelligence_with_no_objections_overrides_the_legacy_text(monkeypatch):
    monkeypatch.setattr("app.services.intelligence.extract.is_current", lambda _memo: True)
    signals = fresh_signals([_memo_with_empty_c04()], now=NOW, day_end=DAY_END)
    assert "objection_open" not in [signal.type for signal in signals]


def test_stale_intelligence_with_no_objections_keeps_the_legacy_text(monkeypatch):
    monkeypatch.setattr("app.services.intelligence.extract.is_current", lambda _memo: False)
    signals = fresh_signals([_memo_with_empty_c04()], now=NOW, day_end=DAY_END)
    assert "objection_open" in [signal.type for signal in signals]


def test_only_a_pending_objection_of_a_reread_memo_is_retracted():
    existing = [
        {"id": "a", "type": "objection_open", "status": "pending", "memo_id": "memo-1", "dedupe_key": "objection:memo-1:other"},
        {"id": "b", "type": "objection_open", "status": "pending", "memo_id": "memo-1", "dedupe_key": "objection:memo-1:price"},
        {"id": "c", "type": "objection_open", "status": "pending", "memo_id": "memo-old", "dedupe_key": "objection:memo-old:other"},
        {"id": "d", "type": "objection_open", "status": "done", "memo_id": "memo-1", "dedupe_key": "objection:memo-1:timing"},
        {"id": "e", "type": "going_cold", "status": "pending", "memo_id": "memo-1", "dedupe_key": "cold:42"},
    ]
    kept = {"objection:memo-1:price"}
    assert retracted_objection_ids(existing, memo_ids={"memo-1"}, fresh_keys=kept) == ["a"]


# --- T5: HOY_LEAD_TIERS_ENABLED wiring through fresh_signals ---


def _no_answer_memo(days_ago: int) -> dict:
    return {
        "id": "memo-na",
        "hubspot_contact_id": "42",
        "capture_started_at": (NOW - timedelta(days=days_ago)).isoformat().replace("+00:00", "Z"),
        "extraction": {},
        "screening_outcome": "no_response",
    }


def test_flag_off_never_produces_callback_no_answer_even_past_the_default_threshold():
    signals = fresh_signals([_no_answer_memo(5)], now=NOW, day_end=DAY_END, lead_tiers_enabled=False)
    assert signals == []


def test_flag_on_produces_callback_no_answer_after_the_configured_days():
    signals = fresh_signals(
        [_no_answer_memo(3)], now=NOW, day_end=DAY_END, lead_tiers_enabled=True, callback_after_days=2,
    )
    assert [signal.type for signal in signals] == ["callback_no_answer"]
    assert signals[0].payload["days_since"] == 3


def test_flag_on_attaches_heat_to_the_signal_payload_flag_off_does_not():
    memo = {
        "id": "memo-hot",
        "hubspot_contact_id": "42",
        "capture_started_at": (NOW - timedelta(days=12)).isoformat().replace("+00:00", "Z"),
        "extraction": {"intelligence": {"interest": "high"}},
    }
    off = fresh_signals([memo], now=NOW, day_end=DAY_END, lead_tiers_enabled=False)
    assert "heat" not in off[0].payload
    on = fresh_signals([memo], now=NOW, day_end=DAY_END, lead_tiers_enabled=True)
    assert isinstance(on[0].payload["heat"], int)
    assert on[0].payload["heat"] > 0


def test_never_contacted_signals_needs_complete_coverage_and_no_local_touch():
    assigned = [
        {"contact_id": "1", "contacted": False},
        {"contact_id": "2", "contacted": True},
        {"contact_id": "3", "contacted": False},
    ]
    partial = never_contacted_signals(assigned, connection_id="crm-A", touched_contact_ids=set(), coverage="partial")
    assert partial == []

    complete = never_contacted_signals(assigned, connection_id="crm-A", touched_contact_ids={"3"}, coverage="complete")
    assert [signal.contact_id for signal in complete] == ["1"]
    assert complete[0].type == "never_contacted"


def test_exclude_handoff_contacts_drops_only_those_contacts():
    signals = [
        Signal(type="going_cold", contact_id="1", deal_id=None, source_memo_id="m", due_at=None, payload={}, dedupe_key="a"),
        Signal(type="going_cold", contact_id="2", deal_id=None, source_memo_id="m", due_at=None, payload={}, dedupe_key="b"),
    ]
    kept = exclude_handoff_contacts(signals, {"1"})
    assert [signal.contact_id for signal in kept] == ["2"]
    assert exclude_handoff_contacts(signals, set()) == signals
