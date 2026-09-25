"""Local meeting time. An ambiguous hour is not filled in."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


def local_time_is_ambiguous(year: int, month: int, day: int, hour: int, minute: int, tz_name: str) -> bool:
    zone = ZoneInfo(tz_name)
    first = datetime(year, month, day, hour, minute, tzinfo=zone, fold=0)
    second = datetime(year, month, day, hour, minute, tzinfo=zone, fold=1)
    return first.utcoffset() != second.utcoffset()


def resolve_phrase(phrase: str, *, tz_name: str, on: datetime | None = None) -> dict:
    """Never invent 09:00 or 17:00. Upload time is not a start time."""
    text = " ".join((phrase or "").lower().split())
    if "las cinco" in text and "tarde" not in text and "mañana" not in text and "17" not in text:
        return {"starts_at": None, "precision": "ambiguous", "needs_review": True}
    if on is not None and local_time_is_ambiguous(on.year, on.month, on.day, on.hour, on.minute, tz_name):
        return {"starts_at": None, "precision": "ambiguous", "needs_review": True}
    if on is not None and "17:00" in text:
        zone = ZoneInfo(tz_name)
        local = datetime(on.year, on.month, on.day, 17, 0, tzinfo=zone)
        return {"starts_at": local.isoformat(), "precision": "exact", "needs_review": False}
    if "el martes" in text and "17" not in text and ":" not in text:
        return {"starts_at": None, "precision": "date_only", "needs_review": True}
    return {"starts_at": None, "precision": "unknown", "needs_review": True}
