"""Team metrics: one definition per metric (Head of Sales dashboard, phase H1)."""

from datetime import datetime, timezone

import pytest

from app.services.team_metrics import (
    DEFAULT_USEFUL_CALL_SECONDS,
    Period,
    build_team_metrics,
    classify_call,
    resolve_periods,
    stats_for_calls,
    useful_call_seconds_from,
)


def _dt(*args):
    return datetime(*args, tzinfo=timezone.utc)


def _call(uid, ts, disposition=None, seconds=0, answered=None):
    return {
        "user_id": uid,
        "created_at": ts.isoformat(),
        "call_disposition": disposition,
        "recording_duration": seconds,
        "answered_at": answered,
    }


MEMBERS = [
    {"user_id": "sdr-1", "full_name": "Toni Mora", "email": "toni@x.com", "sales_role": "sdr", "status": "active"},
    {"user_id": "sdr-2", "full_name": "", "email": "dani@x.com", "sales_role": "sdr", "status": "active"},
    {"user_id": "ae-1", "full_name": "Ana", "email": "ana@x.com", "sales_role": "ae", "status": "active"},
    {"user_id": "gone", "full_name": "Old", "email": "old@x.com", "sales_role": "sdr", "status": "disabled"},
]


def test_classify_call_uses_disposition_then_answered_at():
    assert classify_call({"call_disposition": "connected"}) == "connected"
    assert classify_call({"call_disposition": "voicemail"}) == "voicemail"
    assert classify_call({"call_disposition": "busy"}) == "no_answer"
    assert classify_call({"call_disposition": "no_response"}) == "no_answer"
    assert classify_call({"call_disposition": "canceled"}) == "failed"
    # Pre-027 rows have no disposition.
    assert classify_call({"answered_at": "2026-09-01T10:00:00Z"}) == "connected"
    assert classify_call({}) == "unknown"


def test_useful_conversation_needs_connection_and_threshold():
    now = _dt(2026, 9, 10, 10)
    stats = stats_for_calls(
        [
            _call("u", now, "connected", 75),
            _call("u", now, "connected", 30),
            _call("u", now, "voicemail", 90),  # long voicemail is not a conversation
            _call("u", now, "no_answer"),
        ],
        useful_call_seconds=60,
    )
    assert (stats.calls, stats.connected, stats.useful) == (4, 2, 1)
    assert stats.connection_rate == 0.5
    assert stats.useful_rate == 0.5
    assert stats.talk_seconds == 105


def test_rates_are_none_not_zero_without_data():
    stats = stats_for_calls([], useful_call_seconds=60)
    assert stats.connection_rate is None
    assert stats.useful_rate is None


def test_month_to_date_compares_with_same_days_of_previous_month():
    current, previous = resolve_periods("month", _dt(2026, 9, 28, 18, 30))
    assert current.start == _dt(2026, 9, 1)
    assert previous.start == _dt(2026, 8, 1)
    assert previous.end == _dt(2026, 8, 28, 18, 30)


def test_previous_window_never_overlaps_current():
    # 31 March: February is shorter than the elapsed stretch of March.
    current, previous = resolve_periods("month", _dt(2026, 3, 31, 23))
    assert previous.end <= current.start


def test_week_starts_monday_and_quarter_rolls_back_three_months():
    current, previous = resolve_periods("week", _dt(2026, 9, 30, 9))  # Wednesday
    assert current.start == _dt(2026, 9, 28)
    assert previous.start == _dt(2026, 9, 21)
    q_current, q_previous = resolve_periods("quarter", _dt(2026, 2, 10))
    assert q_current.start == _dt(2026, 1, 1)
    assert q_previous.start == _dt(2025, 10, 1)


def test_unknown_preset_is_rejected():
    with pytest.raises(ValueError):
        resolve_periods("year", _dt(2026, 9, 1))


def test_build_team_metrics_splits_periods_and_filters_role():
    current = Period(_dt(2026, 9, 1), _dt(2026, 9, 28))
    previous = Period(_dt(2026, 8, 1), _dt(2026, 8, 28))
    calls = [
        _call("sdr-1", _dt(2026, 9, 2, 10), "connected", 120),
        _call("sdr-1", _dt(2026, 9, 3, 10), "no_answer"),
        _call("sdr-1", _dt(2026, 8, 5, 10), "connected", 20),
        _call("sdr-2", _dt(2026, 9, 9, 10), "voicemail"),
        _call("ae-1", _dt(2026, 9, 9, 10), "connected", 600),
        _call("gone", _dt(2026, 9, 9, 10), "connected", 600),
        _call("stranger", _dt(2026, 9, 9, 10), "connected", 600),
    ]
    out = build_team_metrics(
        members=MEMBERS,
        calls=calls,
        current=current,
        previous=previous,
        useful_call_seconds=60,
        sales_role="sdr",
    )
    names = [m["name"] for m in out["members"]]
    assert names == ["Toni Mora", "dani"]  # most calls first; email fallback for name
    team = out["team"]
    assert team["current"]["calls"] == 3
    assert team["current"]["connected"] == 1
    assert team["current"]["useful"] == 1
    assert team["previous"]["calls"] == 1
    assert team["previous"]["useful"] == 0
    assert team["median"]["people"] == 2
    assert team["median"]["calls"] == 1.5
    assert out["trend"][0]["week_start"] == "2026-08-31"
    assert sum(w["calls"] for w in out["trend"]) == 3


def test_median_ignores_people_without_calls():
    current = Period(_dt(2026, 9, 1), _dt(2026, 9, 28))
    previous = Period(_dt(2026, 8, 1), _dt(2026, 8, 28))
    out = build_team_metrics(
        members=MEMBERS,
        calls=[_call("ae-1", _dt(2026, 9, 9), "connected", 90)],
        current=current,
        previous=previous,
        useful_call_seconds=60,
    )
    assert len(out["members"]) == 3  # everyone active is listed
    assert out["team"]["median"]["people"] == 1
    assert out["team"]["median"]["connection_rate"] == 1.0


def test_useful_call_seconds_setting_falls_back_to_default():
    assert useful_call_seconds_from({"useful_call_seconds": 45}) == 45
    assert useful_call_seconds_from({"useful_call_seconds": "x"}) == DEFAULT_USEFUL_CALL_SECONDS
    assert useful_call_seconds_from({"useful_call_seconds": 0}) == DEFAULT_USEFUL_CALL_SECONDS
    assert useful_call_seconds_from(None) == DEFAULT_USEFUL_CALL_SECONDS
