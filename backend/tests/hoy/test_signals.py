"""F05: Hoy signals stay the spine rules. Priority tier is a different order."""

import os
from datetime import datetime, timedelta, timezone

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-hoy-signals-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-hoy-signals-32")

from app.services.hoy.reasons import due_label, reason
from app.services.hoy.signals import (
    TIER,
    Commitment,
    Signal,
    Touch,
    never_contacted_signal,
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


def test_reason_and_due_label_follow_accept_language():
    due = signals_for_contact([
        _touch(commitments=(Commitment("call", "prospect_request", "Call back", NOW - timedelta(days=1)),)),
    ], now=NOW, day_end=DAY_END)[0]
    assert reason(due, lang="en") == "They asked you to call."
    assert due_label(due.due_at, now=NOW, lang="en") == "Due yesterday"
    cold = signals_for_contact([_touch(interest="high")], now=NOW, day_end=DAY_END)[0]
    assert reason(cold, lang="en").startswith("Showed strong interest")


def test_objection_of_category_other_has_no_category_in_the_reason():
    from app.services.hoy.signals import Signal

    signal = Signal(type="objection_open", contact_id="c", deal_id=None, source_memo_id="m", due_at=None, payload={"category": "other"}, dedupe_key="k")
    assert reason(signal) == "Quedó una objeción sin cerrar."
    assert reason(signal, lang="en") == "An open objection."


# --- T5: HOY_LEAD_TIERS_ENABLED (callback_no_answer, never_contacted, heat, tier order) ---


def test_callback_after_days_is_off_by_default_even_past_the_threshold():
    """The flag off (callback_after_days=None) must equal pre-change behaviour: no card at all."""
    stale_no_answer = signals_for_contact([
        _touch(screening_outcome="no_response", at=NOW - timedelta(days=5)),
    ], now=NOW, day_end=DAY_END)
    assert stale_no_answer == []


def test_callback_no_answer_triggers_exactly_at_the_day_boundary():
    just_under = signals_for_contact([
        _touch(screening_outcome="no_response", at=NOW - timedelta(days=2) + timedelta(minutes=1)),
    ], now=NOW, day_end=DAY_END, callback_after_days=2)
    assert just_under == []

    at_boundary = signals_for_contact([
        _touch(screening_outcome="no_response", at=NOW - timedelta(days=2)),
    ], now=NOW, day_end=DAY_END, callback_after_days=2)
    assert [signal.type for signal in at_boundary] == ["callback_no_answer"]
    assert at_boundary[0].payload["at"] == (NOW - timedelta(days=2)).isoformat()

    voicemail = signals_for_contact([
        _touch(screening_outcome="voicemail", at=NOW - timedelta(days=3)),
    ], now=NOW, day_end=DAY_END, callback_after_days=2)
    assert [signal.type for signal in voicemail] == ["callback_no_answer"]


def test_callback_no_answer_does_not_fire_after_a_real_conversation():
    connected = signals_for_contact([
        _touch(screening_outcome="no_response", at=NOW - timedelta(days=10), memo_id="memo-old"),
        _touch(screening_outcome="connected", at=NOW - timedelta(days=1), memo_id="memo-new", interest="none"),
    ], now=NOW, day_end=DAY_END, callback_after_days=2)
    assert connected == []


def test_never_contacted_signal_has_its_own_dedupe_key_per_connection_and_contact():
    a = never_contacted_signal(contact_id="1", connection_id="crm-A")
    b = never_contacted_signal(contact_id="1", connection_id="crm-B")
    c = never_contacted_signal(contact_id="2", connection_id="crm-A")
    assert a.type == "never_contacted"
    assert len({a.dedupe_key, b.dedupe_key, c.dedupe_key}) == 3


def test_tier_order_matches_the_plan():
    assert TIER["commitment_due"] == 0
    assert TIER["meeting_today"] == 0
    assert TIER["callback_no_answer"] == 1
    assert TIER["no_reply"] == 1
    assert TIER["going_cold"] == 2
    assert TIER["objection_open"] == 3
    assert TIER["never_contacted"] == 4


def test_heat_breaks_ties_within_a_tier_without_moving_any_tier():
    cooler = signals_for_contact([_touch(contact_id="1", interest="high")], now=NOW, day_end=DAY_END)[0]
    hotter = signals_for_contact([_touch(contact_id="2", memo_id="memo-2", interest="high")], now=NOW, day_end=DAY_END)[0]
    from dataclasses import replace

    cooler = replace(cooler, payload={**cooler.payload, "heat": 10})
    hotter = replace(hotter, payload={**hotter.payload, "heat": 90})
    cards, _ = rank_cards([cooler, hotter], now=NOW)
    assert [card.primary.contact_id for card in cards] == ["2", "1"]
def test_a_stored_signal_of_a_type_this_build_does_not_rank_is_skipped_not_fatal():
    from app.services.hoy.signals import Signal

    stale = Signal("legacy_nudge", due_at=None, payload={}, dedupe_key="old:1", contact_id="9", source_memo_id="m9", deal_id=None)
    live = signals_for_contact([_touch(interest="high")], now=NOW, day_end=DAY_END)
    cards, folded = rank_cards([stale, *live], now=NOW)
    assert all(card.primary.type != "legacy_nudge" for card in cards) and cards
    assert rank_cards([stale], now=NOW) == ([], 0)


def test_a_connected_call_the_reading_saw_as_a_bad_moment_asks_for_a_retry():
    from app.services.hoy.signals import screening_from_call
    bad = {"call": {"call_type": "bad_moment"}}
    assert screening_from_call("connected", bad) == "bad_moment"
    assert screening_from_call(None, {"call": {"call_type": "no_conversation"}}) == "no_response"
    assert screening_from_call("voicemail", bad) == "voicemail"  # telephony knows best
    assert screening_from_call("connected", {"call": {"call_type": "follow_up"}}) == "connected"
    assert screening_from_call(None, None) is None


def test_bad_moment_retry_card_says_they_could_not_talk():
    from datetime import datetime, timezone
    from app.services.hoy.reasons import _callback_no_answer
    now = datetime(2026, 9, 26, 10, 0, tzinfo=timezone.utc)
    text = _callback_no_answer({"outcome": "bad_moment", "at": "2026-09-25T10:00:00+00:00"}, "es", now)
    assert text == "Le llamaste ayer y no podía hablar. Vuelve a intentarlo."


def test_a_call_that_dropped_mid_conversation_asks_for_a_retry():
    from datetime import datetime, timezone
    from app.services.hoy.reasons import _callback_no_answer
    from app.services.hoy.signals import screening_from_call
    assert screening_from_call("connected", {"call": {"call_type": "cold_first_contact", "ended_abruptly": True}}) == "cut_off"
    assert screening_from_call("connected", {"call": {"call_type": "cold_first_contact", "ended_abruptly": False}}) == "connected"
    now = datetime(2026, 9, 26, 10, 0, tzinfo=timezone.utc)
    assert _callback_no_answer({"outcome": "cut_off", "at": "2026-09-26T09:00:00+00:00"}, "es", now) == "Se cortó la llamada hoy. Vuelve a llamar."
