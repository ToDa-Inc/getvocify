"""Decide which people are due a daily report email for the local day."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.services.reporting.delivery import period_bounds, send_report_email

SEND_CUTOFF_HOUR = 18
MADRID = "Europe/Madrid"

logger = logging.getLogger(__name__)


def tick_due_report_emails(now: datetime, load_people, load_existing, sender, persist_delivery=None) -> None:
    """Load candidates and deliveries, then run due sends. Load errors are swallowed."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    madrid_now = now.astimezone(ZoneInfo(MADRID))
    if madrid_now.hour < SEND_CUTOFF_HOUR:
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
    if hasattr(sender, "set_recipients"):
        sender.set_recipients(people)
    run_due_report_emails(now, people, existing, sender, persist_delivery=persist_delivery)


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


def _delivery_row_for_period(user_id: str, period_start: str, existing: list[dict]) -> dict | None:
    for row in existing:
        if row.get("user_id") != user_id:
            continue
        if row.get("period_start") != period_start:
            continue
        return row
    return None


def _parse_attempt_at(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        text = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _failed_retry_due(now: datetime, tz_name: str, row: dict) -> bool:
    """Failed delivery is due again only after the local day of the last attempt."""
    attempt = _parse_attempt_at(row.get("last_attempt_at")) or _parse_attempt_at(row.get("created_at"))
    if attempt is None:
        return True
    local_day_start, _end = period_bounds(now, tz_name)
    return attempt < local_day_start


def _skip_period_send(user_id: str, period_start: str, existing: list[dict], now: datetime, tz_name: str) -> bool:
    row = _delivery_row_for_period(user_id, period_start, existing)
    if row is None:
        return False
    status = row.get("delivery_status")
    if status in ("sent", "uncertain"):
        return True
    if status == "failed":
        return not _failed_retry_due(now, tz_name, row)
    return False


def due_report_sends(now: datetime, people: list[dict], existing: list[dict]) -> list[dict]:
    """People due an email for today's local period; sent/uncertain skip; failed retries once per local day."""
    due: list[dict] = []
    for person in people:
        tz_name = person["timezone"]
        if not _is_due_after_cutoff(now, tz_name):
            continue
        period_start = _period_start_iso(now, tz_name)
        if _skip_period_send(person["user_id"], period_start, existing, now, tz_name):
            continue
        due.append(person)
    return due


def run_due_report_emails(
    now: datetime,
    people: list[dict],
    existing: list[dict],
    sender,
    *,
    persist_delivery=None,
) -> None:
    """Call send_report_email once per due person; skips sent/uncertain for the local period."""
    for person in due_report_sends(now, people, existing):
        if not (person.get("email") or "").strip():
            continue
        period_start = _period_start_iso(now, person["timezone"])
        prior = _delivery_row_for_period(person["user_id"], period_start, existing)
        report = {"id": person["report_id"], "revision": person["revision"]}
        result = send_report_email(report, sender, existing=prior)
        status = result.get("delivery_status")
        if persist_delivery is not None and status in ("sent", "failed", "uncertain"):
            persist_delivery(result, person, now=now)
            attempt_at = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
            existing.append(
                {
                    "user_id": person["user_id"],
                    "period_start": period_start,
                    "delivery_status": status,
                    "idempotency_key": result.get("idempotency_key"),
                    "last_attempt_at": attempt_at.isoformat(),
                }
            )


def run_due_reports(now: datetime, people: list[dict], existing: list[dict], send) -> None:
    """Invoke send once per due person; skips sent/uncertain for the local period."""
    for person in due_report_sends(now, people, existing):
        send(person)
