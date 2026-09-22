"""Decide which people are due a daily report email for the local day."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from app.services.reporting.delivery import period_bounds, send_report_email

SEND_CUTOFF_HOUR = 18
MADRID = "Europe/Madrid"

logger = logging.getLogger(__name__)
_last_madrid_report_tick_date: date | None = None


def reset_report_tick_guard() -> None:
    """Tests only: allow another tick the same Madrid local date."""
    global _last_madrid_report_tick_date
    _last_madrid_report_tick_date = None


def tick_due_report_emails(now: datetime, load_people, load_existing, sender) -> None:
    """Load candidates and deliveries, then run due sends. Load errors are swallowed."""
    global _last_madrid_report_tick_date
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    madrid_now = now.astimezone(ZoneInfo(MADRID))
    if madrid_now.hour < SEND_CUTOFF_HOUR:
        return
    if _last_madrid_report_tick_date == madrid_now.date():
        return
    try:
        people = load_people()
    except Exception:
        logger.exception("report tick: load_people failed")
        return
    try:
        existing = load_existing()
    except Exception:
        logger.exception("report tick: load_existing failed")
        return
    if sender is None:
        return
    _last_madrid_report_tick_date = madrid_now.date()
    run_due_report_emails(now, people, existing, sender)


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


def _delivery_for_period(user_id: str, period_start: str, existing: list[dict]) -> dict | None:
    for row in existing:
        if row.get("user_id") != user_id:
            continue
        if row.get("period_start") != period_start:
            continue
        return row
    return None


def run_due_report_emails(now: datetime, people: list[dict], existing: list[dict], sender) -> None:
    """Call send_report_email once per due person; skips sent/uncertain for the local period."""
    for person in due_report_sends(now, people, existing):
        period_start = _period_start_iso(now, person["timezone"])
        prior = _delivery_for_period(person["user_id"], period_start, existing)
        report = {"id": person["report_id"], "revision": person["revision"]}
        send_report_email(report, sender, existing=prior)


def run_due_reports(now: datetime, people: list[dict], existing: list[dict], send) -> None:
    """Invoke send once per due person; skips sent/uncertain for the local period."""
    for person in due_report_sends(now, people, existing):
        send(person)
