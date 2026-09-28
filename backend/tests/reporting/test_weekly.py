"""F13.04: the weekly period is the local working week, and a day not yet observed is a gap, not a zero."""

import os
from datetime import datetime, timezone

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-weekly-reports-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-weekly-reports-32")

import pytest

from app.services.reporting.weekly import (
    day_series,
    week_bounds,
    weekly_due,
    weekly_due_somewhere,
    weekly_self_snapshot,
)

UTC = timezone.utc
MADRID = "Europe/Madrid"
FRIDAY_1805 = datetime(2026, 9, 25, 16, 5, tzinfo=UTC)


def test_week_is_monday_to_saturday_local_and_half_open():
    start, end = week_bounds(FRIDAY_1805, MADRID)
    assert start == datetime(2026, 9, 20, 22, 0, tzinfo=UTC)
    assert end == datetime(2026, 9, 25, 22, 0, tzinfo=UTC)


def test_week_after_the_dst_change_starts_at_local_midnight():
    start, end = week_bounds(datetime(2026, 10, 30, 17, 30, tzinfo=UTC), MADRID)
    assert start == datetime(2026, 10, 25, 23, 0, tzinfo=UTC)
    assert end == datetime(2026, 10, 30, 23, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "instant, expected",
    [
        (datetime(2026, 9, 23, 12, 0, tzinfo=UTC), False),  # Wednesday: due nowhere
        (datetime(2026, 9, 25, 3, 59, tzinfo=UTC), False),  # before Friday 18:00 in UTC+14
        (datetime(2026, 9, 25, 4, 0, tzinfo=UTC), True),  # Friday 18:00 in UTC+14
        (datetime(2026, 9, 26, 12, 0, tzinfo=UTC), True),
        (datetime(2026, 9, 28, 11, 59, tzinfo=UTC), True),  # still Sunday in UTC-12
        (datetime(2026, 9, 28, 12, 0, tzinfo=UTC), False),
    ],
)
def test_the_tick_only_looks_for_weekly_reports_while_some_zone_is_due(instant, expected):
    assert weekly_due_somewhere(instant) is expected


def test_weekend_ticks_report_the_same_week_as_friday():
    friday = week_bounds(FRIDAY_1805, MADRID)
    assert week_bounds(datetime(2026, 9, 26, 9, 0, tzinfo=UTC), MADRID) == friday
    assert week_bounds(datetime(2026, 9, 27, 21, 0, tzinfo=UTC), MADRID) == friday


@pytest.mark.parametrize(
    "instant, expected",
    [
        (datetime(2026, 9, 25, 15, 59, tzinfo=UTC), False),
        (datetime(2026, 9, 25, 16, 0, tzinfo=UTC), True),
        (datetime(2026, 9, 26, 9, 0, tzinfo=UTC), True),
        (datetime(2026, 9, 27, 21, 59, tzinfo=UTC), True),
        (datetime(2026, 9, 27, 22, 0, tzinfo=UTC), False),
        (datetime(2026, 9, 24, 17, 0, tzinfo=UTC), False),
    ],
)
def test_weekly_is_due_from_friday_1800_local_until_monday(instant, expected):
    assert weekly_due(instant, MADRID) is expected


def test_weekly_due_follows_the_recipient_zone():
    # 18:05 in Madrid is 12:05 in New York: not due there yet.
    assert weekly_due(FRIDAY_1805, "America/New_York") is False


def _row(at: str, screening: str, meeting: bool = False) -> dict:
    return {"observed_at": at, "screening": screening, "meeting_agreed": meeting}


def test_day_series_counts_connected_and_meetings_per_local_day():
    start, end = week_bounds(FRIDAY_1805, MADRID)
    rows = [
        _row("2026-09-21T08:00:00+00:00", "connected", True),
        _row("2026-09-21T09:00:00+00:00", "voicemail"),
        _row("2026-09-23T09:00:00+00:00", "connected"),
        _row("2026-09-20T21:30:00+00:00", "connected"),
    ]
    series = day_series(rows, start=start, end=end, tz_name=MADRID, generated_at=FRIDAY_1805)
    assert [day["date"] for day in series] == [
        "2026-09-21", "2026-09-22", "2026-09-23", "2026-09-24", "2026-09-25",
    ]
    assert series[0] == {"date": "2026-09-21", "connected_calls": 1, "meetings_agreed": 1, "covered": True}
    assert series[1] == {"date": "2026-09-22", "connected_calls": 0, "meetings_agreed": 0, "covered": True}
    assert series[2]["connected_calls"] == 1


def test_a_day_after_generation_is_a_gap_not_a_zero():
    start, end = week_bounds(FRIDAY_1805, MADRID)
    thursday_noon = datetime(2026, 9, 24, 10, 0, tzinfo=UTC)
    series = day_series([], start=start, end=end, tz_name=MADRID, generated_at=thursday_noon)
    assert series[3]["covered"] is True
    assert series[4] == {"date": "2026-09-25", "connected_calls": None, "meetings_agreed": None, "covered": False}


def _memo(memo_id: str, at: str, screening: str, meeting: bool = False) -> dict:
    intel = {"meeting": {"agreed": True}} if meeting else {}
    return {
        "id": memo_id,
        "screening_outcome": screening,
        "capture_started_at": at,
        "created_at": at,
        "extraction": {"intelligence": intel},
    }


def _pattern(category: str, resolution: str, at: str, *, superseded: bool = False) -> dict:
    return {
        "category": category,
        "kind": "objection",
        "resolution": resolution,
        "superseded": superseded,
        "created_at": at,
    }


def test_weekly_snapshot_uses_the_daily_aggregator_and_adds_series_and_objections():
    start, end = week_bounds(FRIDAY_1805, MADRID)
    memos = [
        _memo("m-1", "2026-09-21T08:00:00+00:00", "connected", meeting=True),
        _memo("m-2", "2026-09-21T09:00:00+00:00", "voicemail"),
        _memo("m-3", "2026-09-23T09:00:00+00:00", "connected"),
        _memo("m-old", "2026-09-18T09:00:00+00:00", "connected"),
    ]
    patterns = [
        _pattern("price", "resolved", "2026-09-21T08:05:00+00:00"),
        _pattern("price", "open", "2026-09-23T09:05:00+00:00"),
        _pattern("timing", "unknown", "2026-09-23T09:06:00+00:00"),
        _pattern("price", "open", "2026-09-23T09:07:00+00:00", superseded=True),
    ]
    snap = weekly_self_snapshot(
        memos=memos,
        pattern_rows=patterns,
        period_start=start,
        period_end=end,
        timezone=MADRID,
        generated_at=FRIDAY_1805,
        outcomes={"coverage": "unavailable"},
    )
    assert snap["scope"] == "self"
    assert snap["report_type"] == "weekly"
    assert snap["period_start"] == start.isoformat()
    assert snap["period_end"] == end.isoformat()
    assert snap["generated_at"] == FRIDAY_1805.isoformat()
    assert snap["metrics"]["attempts"] == 3
    assert snap["metrics"]["connected_calls"] == 2
    assert snap["metrics"]["meetings_agreed"] == 1
    assert snap["metrics"]["deals_won"] is None
    assert snap["coverage"]["crm_outcomes"] == "unavailable"
    assert len(snap["series"]) == 5
    assert all(day["covered"] for day in snap["series"])
    assert snap["objections"] == [
        {"name": "price", "count": 2, "resolved": 1, "open": 1, "unknown": 0},
        {"name": "timing", "count": 1, "resolved": 0, "open": 0, "unknown": 1},
    ]
    assert snap["coverage"]["objections"] == "complete"
    assert snap["coaching"] is None


def test_unreadable_objections_are_unavailable_not_empty():
    start, end = week_bounds(FRIDAY_1805, MADRID)
    snap = weekly_self_snapshot(
        memos=[_memo("m-1", "2026-09-21T08:00:00+00:00", "connected")],
        pattern_rows=None,
        period_start=start,
        period_end=end,
        timezone=MADRID,
        generated_at=FRIDAY_1805,
        outcomes={"coverage": "unavailable"},
    )
    assert snap["objections"] is None
    assert snap["coverage"]["objections"] == "unavailable"
