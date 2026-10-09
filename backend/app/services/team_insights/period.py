"""Head of Sales phase 2: which stretch of time the team page reads, and what it compares with.

Days are Madrid days, like the rest of team_insights. "week" is exactly
aggregate.madrid_week_bounds(), so a caller that sends no period sees what it saw before.
The previous window always covers the same elapsed time as the current one (the 1st-28th
of this month is compared with the 1st-28th of last month), never more.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

_MADRID = ZoneInfo("Europe/Madrid")

PERIOD_PRESETS = ("week", "month", "last_30", "quarter")
DEFAULT_PERIOD = "week"


@dataclass(frozen=True)
class Window:
    start: datetime  # inclusive, UTC
    end: datetime  # exclusive, UTC

    def as_dict(self) -> dict:
        return {"start": self.start.isoformat(), "end": self.end.isoformat()}


def _madrid_midnight(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=_MADRID).astimezone(timezone.utc)


def _shift_months(day: date, months: int) -> date:
    index = day.year * 12 + (day.month - 1) + months
    return date(index // 12, index % 12 + 1, 1)


def period_windows(preset: str, *, now: datetime | None = None) -> tuple[Window, Window]:
    """(current, previous) for a preset. Raises ValueError for an unknown preset."""
    instant = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    today = instant.astimezone(_MADRID).date()
    if preset == "last_30":
        current = Window(instant - timedelta(days=30), instant)
        return current, Window(current.start - timedelta(days=30), current.start)
    if preset == "week":
        first = today - timedelta(days=today.weekday())
        previous_first = first - timedelta(days=7)
        # Same bounds as madrid_week_bounds: the whole ISO week (the future part is empty).
        current = Window(_madrid_midnight(first), _madrid_midnight(first + timedelta(days=7)))
    elif preset == "month":
        first = today.replace(day=1)
        previous_first = _shift_months(first, -1)
        current = Window(_madrid_midnight(first), instant)
    elif preset == "quarter":
        first = date(today.year, 3 * ((today.month - 1) // 3) + 1, 1)
        previous_first = _shift_months(first, -3)
        current = Window(_madrid_midnight(first), instant)
    else:
        raise ValueError(f"unknown period: {preset}")
    elapsed = min(instant, current.end) - current.start
    previous_start = _madrid_midnight(previous_first)
    return current, Window(previous_start, min(previous_start + elapsed, current.start))
