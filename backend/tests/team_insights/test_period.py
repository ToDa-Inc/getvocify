"""Head of Sales phase 2: period presets and the comparable previous stretch (Madrid days)."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-team-period-32")

from datetime import datetime, timezone

import pytest

from app.services.team_insights.aggregate import madrid_week_bounds
from app.services.team_insights.period import PERIOD_PRESETS, period_windows


def _utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


NOW = _utc(2026, 9, 28, 16, 30)  # Monday 18:30 in Madrid


def test_week_keeps_the_existing_madrid_week_so_default_behaviour_is_unchanged():
    current, _ = period_windows("week", now=NOW)
    assert (current.start, current.end) == madrid_week_bounds(now=NOW)


def test_previous_window_has_the_same_elapsed_length_as_the_current_one():
    current, previous = period_windows("month", now=NOW)
    assert current.start == _utc(2026, 8, 31, 22)  # 1 Sep 00:00 Madrid
    assert previous.start == _utc(2026, 7, 31, 22)  # 1 Aug 00:00 Madrid
    assert previous.end - previous.start == NOW - current.start
    assert previous.end <= current.start


def test_week_previous_is_last_week_up_to_the_same_moment():
    current, previous = period_windows("week", now=_utc(2026, 9, 30, 10))  # Wednesday
    assert previous.start == _utc(2026, 9, 20, 22)
    assert previous.end == _utc(2026, 9, 23, 10)


def test_quarter_and_last_30():
    current, previous = period_windows("quarter", now=NOW)
    assert current.start == _utc(2026, 6, 30, 22)  # 1 Jul Madrid (CEST)
    assert previous.start == _utc(2026, 3, 31, 22)  # 1 Apr Madrid (CEST)
    last, before = period_windows("last_30", now=NOW)
    assert last.end == NOW and (last.end - last.start).days == 30
    assert before.end == last.start and (before.end - before.start).days == 30


def test_previous_never_overlaps_current_when_the_previous_month_is_shorter():
    current, previous = period_windows("month", now=_utc(2026, 3, 31, 20))
    assert previous.end <= current.start


def test_unknown_preset_is_rejected():
    assert set(PERIOD_PRESETS) == {"week", "month", "last_30", "quarter"}
    with pytest.raises(ValueError):
        period_windows("year", now=NOW)
