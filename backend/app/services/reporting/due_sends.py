"""Decide which people are due a daily report email for the local day."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.services.reporting.delivery import period_bounds

SEND_CUTOFF_HOUR = 18


def _local_hour(now: datetime, tz_name: str) -> tuple[int, int]:
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    local = now.astimezone(ZoneInfo(tz_name))
    return local.hour, local.minute


def _is_due_after_cutoff(now: datetime, tz_name: str) -> bool:
    hour, _minute = _local_hour(now, tz_name)
    return hour >= SEND_CUTOFF_HOUR


def _period_start_iso(now: datetime, tz_name: str) -> str:
    start, _end = period_bounds(now, tz_name)
    return start.isoformat()


def _skip_period_send(user_id: str, period_start: str, existing: list[dict]) -> bool:
    for row in existing:
        if row.get("user_id") != user_id:
            continue
        if row.get("period_start") != period_start:
            continue
        status = row.get("delivery_status")
        if status in ("sent", "uncertain"):
            return True
    return False


def due_report_sends(now: datetime, people: list[dict], existing: list[dict]) -> list[dict]:
    """People due an email for today's local period; sent/uncertain skip, failed may retry."""
    due: list[dict] = []
    for person in people:
        tz_name = person["timezone"]
        if not _is_due_after_cutoff(now, tz_name):
            continue
        period_start = _period_start_iso(now, tz_name)
        if _skip_period_send(person["user_id"], period_start, existing):
            continue
        due.append(person)
    return due


def run_due_reports(now: datetime, people: list[dict], existing: list[dict], send) -> None:
    """Invoke send once per due person; skips sent/uncertain for the local period."""
    for person in due_report_sends(now, people, existing):
        send(person)
