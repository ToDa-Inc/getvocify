"""F05: Hoy signals stay the spine rules. Priority tier is a different order."""

import os
from datetime import datetime, timedelta, timezone

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-hoy-signals-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-hoy-signals-32")

from app.services.hoy.reasons import due_label, reason
from app.services.hoy.signals import (
    Commitment,
    Touch,
    rank_cards,
    reconcile,
    signals_for_contact,
    touch_from_intelligence,
)

NOW = datetime(2026, 9, 22, 10, 0, tzinfo=timezone.utc)
DAY_END = datetime(2026, 9, 22, 23, 59, tzinfo=timezone.utc)


def _touch(**overrides) -> Touch:
    base = dict(
        memo_id="memo-1",
        contact_id="42",
        deal_id="deal-7",
        at=NOW - timedelta(days=12),
        connection_id="crm-A",
    )
    base.update(overrides)
    return Touch(**base)


def test_a_due_commitment_is_a_card_and_a_future_one_silences_going_cold():
    due = signals_for_contact([
        _touch(commitments=(Commitment("call", "rep_promise", "Llamar", NOW - timedelta(hours=1)),)),
    ], now=NOW, day_end=DAY_END)
    assert due[0].type == "commitment_due"
    assert due[0].connection_id == "crm-A"
    assert reason(due[0]) == "Quedaste en llamarle."
    assert due_label(due[0].due_at, now=NOW) == "Hoy"

    future = signals_for_contact([
        _touch(
            interest="high",
            commitments=(Commitment("call", "rep_promise", "Llamar", NOW + timedelta(days=3)),),
        ),
    ], now=NOW, day_end=DAY_END)
    assert future == []


def test_none_interest_and_a_closed_deal_stay_silent():
    assert signals_for_contact([_touch(interest="none")], now=NOW, day_end=DAY_END) == []
    assert signals_for_contact([_touch(interest="high", deal_closed=True)], now=NOW, day_end=DAY_END) == []


def test_ten_silent_days_go_cold_and_a_newer_touch_clears_the_old_one():
    cold = signals_for_contact([_touch(interest="high")], now=NOW, day_end=DAY_END)
    assert cold[0].type == "going_cold"
    assert cold[0].payload["days_silent"] == 12
    assert reason(cold[0]).startswith("Mostró mucho interés")

    fresh = signals_for_contact([
        _touch(interest="high"),
        _touch(memo_id="memo-2", at=NOW - timedelta(days=1), interest="high"),
    ], now=NOW, day_end=DAY_END)
    assert fresh == []


def test_one_card_per_contact_orders_overdue_then_hot_then_objection_and_folds_the_rest():
    overdue = signals_for_contact([
        _touch(contact_id="1", commitments=(Commitment("email", "rep_promise", "Enviar el caso.", NOW - timedelta(days=2)),)),
    ], now=NOW, day_end=DAY_END)
    hot = signals_for_contact([_touch(contact_id="2", memo_id="memo-hot", interest="high")], now=NOW, day_end=DAY_END)
    objection = signals_for_contact([
        _touch(contact_id="3", memo_id="memo-obj", at=NOW, interest="low", objections=(("price", "está caro"),)),
    ], now=NOW, day_end=DAY_END)
    extra = [
        signals_for_contact([
            _touch(contact_id=str(index), memo_id=f"m-{index}", interest="medium"),
        ], now=NOW, day_end=DAY_END)[0]
        for index in range(4, 12)
    ]
    cards, folded = rank_cards([*overdue, *hot, *objection, *extra], now=NOW)
    assert len(cards) == 7
    assert folded == 4
    assert cards[0].primary.type == "commitment_due"
    assert cards[1].primary.payload["interest"] == "high"
    assert reason(objection[0]) == "Quedó una objeción de precio sin cerrar."
    same = signals_for_contact([
        _touch(
            commitments=(Commitment("call", "prospect_request", "Llamar", NOW - timedelta(hours=2)),),
            interest="low",
            objections=(("timing", "el mes que viene"),),
            at=NOW,
        ),
    ], now=NOW, day_end=DAY_END)
    grouped, _ = rank_cards(same, now=NOW)
    assert grouped[0].primary.type == "commitment_due"
    assert grouped[0].supporting[0].type == "objection_open"


def test_reconcile_does_not_resurrect_a_dismissed_key_and_resolves_a_stale_pending_one():
    fresh = signals_for_contact([_touch(interest="high")], now=NOW, day_end=DAY_END)
    inserted, resolved = reconcile({fresh[0].dedupe_key: "dismissed", "cold:old": "pending"}, fresh)
    assert inserted == []
    assert resolved == {"cold:old"}


def test_unknown_interest_and_a_resolved_objection_do_not_open_a_card():
    missing = touch_from_intelligence(
        memo_id="memo-1",
        contact_id="42",
        deal_id=None,
        at=None,
        history_complete=False,
        legacy_objections="está caro",
    )
    assert missing is None
    resolved = touch_from_intelligence(
        memo_id="memo-1",
        contact_id="42",
        deal_id="deal-7",
        at=NOW,
        connection_id="crm-A",
        history_complete=True,
        legacy_objections="está caro",
        intelligence={
            "interest": None,
            "objections": [{"state": "resolved", "category": "price", "quote": "está caro"}],
        },
    )
    assert signals_for_contact([resolved], now=NOW, day_end=DAY_END) == []
    open_objection = touch_from_intelligence(
        memo_id="memo-1",
        contact_id="42",
        deal_id="deal-7",
        at=NOW,
        intelligence={"interest": "low", "objections": [{"state": "open", "category": "price", "quote": "está caro"}]},
    )
    opened = signals_for_contact([open_objection], now=NOW, day_end=DAY_END)
    assert opened[0].type == "objection_open"
    assert opened[0].payload["quote"] == "está caro"
