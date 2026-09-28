"""Lista 4 T2 (E8): a hot contact comes back to Hoy on the date its stopper sets, not every day."""

import os
from datetime import datetime, timedelta, timezone

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-hoy-cadence-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-hoy-cadence-32")

import pytest

from app.services.hoy.cadence import (
    DEFAULT_WAIT_DAYS,
    followup_due_at,
    parse_overrides,
    stopper_for,
)
from app.services.hoy.reasons import followup_upcoming_text, reason
from app.services.hoy.signals import TIER, Commitment, Touch, rank_cards, signals_for_contact

CALL_AT = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)


def _touch(**overrides) -> Touch:
    base = dict(memo_id="memo-1", contact_id="42", deal_id=None, at=CALL_AT, connection_id="crm-A")
    base.update(overrides)
    return Touch(**base)


def _day_end(day: datetime) -> datetime:
    return day.replace(hour=23, minute=59, second=59)


@pytest.mark.parametrize(
    ("touch", "stopper", "days"),
    [
        (dict(interest="high"), "interest_high", 2),
        (dict(interest="medium"), "interest_medium", 5),
        (dict(interest="low"), "interest_low", 30),
        (dict(interest="high", objections=(("price", "Es caro"),)), "price", 7),
        (dict(interest="high", objections=(("authority", "Lo decide mi jefe"),)), "authority", 5),
        (dict(interest="medium", objections=(("trust", "No os conozco"),)), "trust", 7),
        (dict(interest="medium", objections=(("competitor", "Usamos X"),)), "competitor", 14),
        (dict(interest="medium", objections=(("status_quo", "Estamos bien"),)), "status_quo", 14),
        (dict(interest="high", objections=(("timing", "En enero"),)), "timing", 21),
        (dict(interest="low", objections=(("other", "Algo"),)), "other", 7),
    ],
)
def test_the_full_e8_cadence_table(touch, stopper, days):
    subject = _touch(**touch)
    assert stopper_for(subject) == stopper
    assert DEFAULT_WAIT_DAYS[stopper] == days
    assert followup_due_at(subject) == CALL_AT + timedelta(days=days)


def test_the_latest_open_objection_decides_the_stopper():
    subject = _touch(interest="high", objections=(("price", "caro"), ("timing", "en enero")))
    assert stopper_for(subject) == "timing"


def test_an_unknown_category_counts_as_other():
    assert stopper_for(_touch(interest="high", objections=(("weird", "x"),))) == "other"


def test_no_interest_never_comes_back_and_unknown_interest_stays_unknown():
    assert stopper_for(_touch(interest="none")) == "interest_none"
    assert followup_due_at(_touch(interest="none")) is None
    assert followup_due_at(_touch(interest="none", objections=(("price", "caro"),))) is None
    assert stopper_for(_touch()) is None
    assert followup_due_at(_touch()) is None


def test_company_overrides_replace_only_their_own_stopper():
    overrides = {"price": 3}
    assert followup_due_at(_touch(interest="high", objections=(("price", "caro"),)), overrides) == CALL_AT + timedelta(days=3)
    assert followup_due_at(_touch(interest="high"), overrides) == CALL_AT + timedelta(days=2)


def test_parse_overrides_keeps_only_known_stoppers_with_days_1_to_90():
    raw = {
        "price": 3, "timing": 90, "trust": 0, "competitor": 91, "authority": "5",
        "status_quo": True, "interest_none": 4, "nope": 2, "other": 1,
    }
    assert parse_overrides(raw) == {"price": 3, "timing": 90, "other": 1}
    assert parse_overrides(None) == {}
    assert parse_overrides(["price", 3]) == {}


def test_the_date_the_rep_picked_beats_the_table():
    picked = CALL_AT + timedelta(days=12)
    subject = _touch(interest="high", objections=(("price", "caro"),))
    assert followup_due_at(subject, rep_followup_at=picked) == picked
    assert followup_due_at(_touch(interest="high", followup_at=picked)) == picked
    # Even a contact the table would never bring back, if the rep chose a date.
    assert followup_due_at(_touch(interest="none", followup_at=picked)) == picked


def test_a_closing_outcome_never_comes_back():
    for outcome in ("not_interested", "disqualified", "meeting_booked"):
        subject = _touch(interest="high", rep_outcome=outcome, followup_at=CALL_AT + timedelta(days=3))
        assert followup_due_at(subject) is None
    assert followup_due_at(_touch(interest="high", rep_outcome="follow_up")) == CALL_AT + timedelta(days=2)


# --- signals_for_contact with cadence on ---------------------------------------------


def test_cadence_replaces_going_cold_and_objection_open_with_one_followup_due():
    touch = _touch(interest="high", objections=(("price", "Es caro"),))
    now = CALL_AT + timedelta(days=8)
    old = signals_for_contact([touch], now=now, day_end=_day_end(now))
    assert [signal.type for signal in old] == ["objection_open"]

    new = signals_for_contact([touch], now=now, day_end=_day_end(now), cadence={})
    assert [signal.type for signal in new] == ["followup_due"]
    signal = new[0]
    assert signal.dedupe_key == f"followup:memo-1:{(CALL_AT + timedelta(days=7)).date().isoformat()}"
    assert signal.due_at == CALL_AT + timedelta(days=7)
    assert signal.payload["stopper"] == "price"
    assert signal.payload["interest"] == "high"
    assert signal.payload["days_since"] == 8
    assert signal.payload["category"] == "price"
    assert signal.payload["quote"] == "Es caro"
    assert signal.payload["due_at"] == (CALL_AT + timedelta(days=7)).isoformat()
    assert TIER["followup_due"] == 2


def test_the_day_after_the_call_nothing_comes_back():
    touch = _touch(interest="high", objections=(("price", "Es caro"),))
    now = CALL_AT + timedelta(days=1)
    assert signals_for_contact([touch], now=now, day_end=_day_end(now), cadence={}) == []
    # The eve of its date: still nothing. Its own day: from the morning on.
    eve = CALL_AT + timedelta(days=6)
    assert signals_for_contact([touch], now=eve, day_end=_day_end(eve), cadence={}) == []
    morning = (CALL_AT + timedelta(days=7)).replace(hour=7)
    assert [s.type for s in signals_for_contact([touch], now=morning, day_end=_day_end(morning), cadence={})] == ["followup_due"]


def test_cadence_overrides_move_the_date():
    touch = _touch(interest="high", objections=(("price", "Es caro"),))
    now = CALL_AT + timedelta(days=3)
    assert signals_for_contact([touch], now=now, day_end=_day_end(now), cadence={}) == []
    assert [s.type for s in signals_for_contact([touch], now=now, day_end=_day_end(now), cadence={"price": 3})] == ["followup_due"]


def test_the_rep_date_decides_when_it_comes_back():
    touch = _touch(interest="high", followup_at=CALL_AT + timedelta(days=10))
    early = CALL_AT + timedelta(days=5)
    assert signals_for_contact([touch], now=early, day_end=_day_end(early), cadence={}) == []
    due = CALL_AT + timedelta(days=10)
    assert [s.type for s in signals_for_contact([touch], now=due, day_end=_day_end(due), cadence={})] == ["followup_due"]


def test_a_disqualified_or_not_interested_contact_never_gets_a_followup():
    now = CALL_AT + timedelta(days=40)
    for outcome in ("not_interested", "disqualified"):
        touch = _touch(interest="high", objections=(("price", "caro"),), rep_outcome=outcome)
        assert signals_for_contact([touch], now=now, day_end=_day_end(now), cadence={}) == []


def test_commitments_keep_their_suppression_under_cadence():
    now = CALL_AT + timedelta(days=30)
    future = _touch(
        interest="high",
        commitments=(Commitment("call", "prospect_request", "Llamar en noviembre", now + timedelta(days=20)),),
    )
    assert signals_for_contact([future], now=now, day_end=_day_end(now), cadence={}) == []
    due = _touch(interest="high", commitments=(Commitment("call", "rep_promise", "Llamar", now - timedelta(hours=1)),))
    assert [s.type for s in signals_for_contact([due], now=now, day_end=_day_end(now), cadence={})] == ["commitment_due"]


def test_a_callback_no_answer_suppresses_the_followup():
    now = CALL_AT + timedelta(days=30)
    touch = _touch(interest="high", screening_outcome="no_response")
    out = signals_for_contact([touch], now=now, day_end=_day_end(now), callback_after_days=2, cadence={})
    assert [s.type for s in out] == ["callback_no_answer"]


def test_a_closed_deal_produces_nothing_under_cadence():
    now = CALL_AT + timedelta(days=30)
    touch = _touch(interest="high", deal_closed=True)
    assert signals_for_contact([touch], now=now, day_end=_day_end(now), cadence={}) == []


def test_only_the_latest_touch_counts():
    older = _touch(memo_id="m-old", interest="high", at=CALL_AT - timedelta(days=30))
    latest = _touch(memo_id="m-new", interest="medium")
    now = CALL_AT + timedelta(days=5)
    out = signals_for_contact([older, latest], now=now, day_end=_day_end(now), cadence={})
    assert [(s.type, s.dedupe_key) for s in out] == [("followup_due", f"followup:m-new:{(CALL_AT + timedelta(days=5)).date().isoformat()}")]


def test_followup_ranks_after_tasks_and_before_never_contacted():
    now = CALL_AT + timedelta(days=8)
    followup = signals_for_contact(
        [_touch(interest="high", objections=(("price", "caro"),))], now=now, day_end=_day_end(now), cadence={},
    )
    task = signals_for_contact(
        [_touch(memo_id="m2", contact_id="43", commitments=(Commitment("call", "rep_promise", "Llamar", now),))],
        now=now, day_end=_day_end(now), cadence={},
    )
    cards, _ = rank_cards(followup + task, now=now)
    assert [card.primary.type for card in cards] == ["commitment_due", "followup_due"]


# --- wording ------------------------------------------------------------------------


def _followup(now, **touch):
    return signals_for_contact([_touch(**touch)], now=now, day_end=_day_end(now), cadence={})[0]


def test_followup_reason_is_worded_by_its_stopper():
    now = CALL_AT + timedelta(days=8)
    price = _followup(now, interest="high", objections=(("price", "Es caro"),))
    assert reason(price, now=now) == "Le interesó; frenó por precio (hace 8 días)."
    assert reason(price, lang="en", now=now) == "Was interested; stalled on price (8 days ago)."
    medium = _followup(now, interest="medium")
    assert reason(medium, now=now) == "Mostró interés hace 8 días, sin siguiente paso."
    assert reason(medium, lang="en", now=now) == "Showed interest 8 days ago, no next step."
    high = _followup(now, interest="high")
    assert reason(high, now=now) == "Mostró mucho interés hace 8 días, sin siguiente paso."


def test_followup_reason_counts_days_at_render_time_and_says_one_day():
    now = CALL_AT + timedelta(days=2)
    signal = _followup(now, interest="high")
    assert reason(signal, now=now) == "Mostró mucho interés hace 2 días, sin siguiente paso."
    assert reason(signal, now=now + timedelta(days=3)) == "Mostró mucho interés hace 5 días, sin siguiente paso."
    one = _followup(CALL_AT + timedelta(days=1), interest="high", followup_at=CALL_AT + timedelta(days=1))
    assert reason(one, now=CALL_AT + timedelta(days=1)) == "Mostró mucho interés hace 1 día, sin siguiente paso."
    assert reason(one, lang="en", now=CALL_AT + timedelta(days=1)) == "Showed strong interest 1 day ago, no next step."


def test_followup_reason_without_a_known_interest_says_the_rep_chose_the_date():
    now = CALL_AT + timedelta(days=4)
    signal = _followup(now, followup_at=CALL_AT + timedelta(days=4))
    assert reason(signal, now=now) == "Quedaste en volver a llamarle."
    assert reason(signal, lang="en", now=now) == "You planned to call them back."


def test_upcoming_text_names_the_stopper():
    assert followup_upcoming_text("price") == "Seguimiento · frenó por precio"
    assert followup_upcoming_text("price", lang="en") == "Follow-up · stalled on price"
    assert followup_upcoming_text("interest_high") == "Seguimiento · interés alto, sin siguiente paso"
    assert followup_upcoming_text(None) == "Seguimiento"
