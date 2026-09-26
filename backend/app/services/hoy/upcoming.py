"""Próximas: C04 commitments due from tomorrow on, in the rep's zone. No I/O."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.services.hoy.materialize import _commitments, _intelligence, as_dt, fresh_signals
from app.services.hoy.names import clean_name, lookup, memo_directory

DEFAULT_DAYS = 7
MIN_DAYS = 1
MAX_DAYS = 14
DEFAULT_TZ = "Europe/Madrid"


def _zone(tz_name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(str(tz_name or DEFAULT_TZ))
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_TZ)


def local_midnight(now: datetime, tz_name: str | None, *, days: int = 0) -> datetime:
    """00:00 of the rep's local day `days` after today, in UTC. DST-safe: built from the local date."""
    zone = _zone(tz_name)
    day = now.astimezone(zone).date() + timedelta(days=days)
    return datetime.combine(day, time(), tzinfo=zone).astimezone(timezone.utc)


def _stored_commitment(memo: dict | None, signal) -> dict:
    """The extracted item behind a Hoy signal, for what the signal payload drops (precision, CRM task)."""
    for item in _commitments(_intelligence(memo or {})):
        if (
            (item.get("kind") or "other") == signal.payload.get("kind")
            and (item.get("text") or "") == signal.payload.get("text")
            and as_dt(item.get("due_at")) == signal.due_at
        ):
            return item
    return {}


def upcoming_commitments(memos: list[dict], *, now: datetime, tz_name: str | None, days: int = DEFAULT_DAYS) -> list[dict]:
    """Hoy's commitment signals due in [tomorrow 00:00, tomorrow + days 00:00) local, one per Hoy key."""
    start = local_midnight(now, tz_name, days=1)
    end = local_midnight(now, tz_name, days=1 + days)
    by_id = {str(memo.get("id") or ""): memo for memo in memos}
    directory = memo_directory(memos)
    seen: set[str] = set()
    rows: list[dict] = []
    for signal in fresh_signals(memos, now=now, day_end=end):
        if signal.type != "commitment_due" or signal.due_at is None or not start <= signal.due_at < end:
            continue
        if signal.dedupe_key in seen:
            continue
        seen.add(signal.dedupe_key)
        item = _stored_commitment(by_id.get(signal.source_memo_id), signal)
        name, company = lookup(directory, signal.source_memo_id, signal.contact_id)
        rows.append({
            "memo_id": signal.source_memo_id,
            "contact_id": signal.contact_id,
            "contact_name": name,
            "company_name": company,
            "text": clean_name(signal.payload.get("text")),
            "due_at": signal.due_at.isoformat(),
            "precision": item.get("temporal_precision") or item.get("precision") or None,
            "crm_task_id": item.get("crm_task_id") or None,
        })
    rows.sort(key=lambda row: (as_dt(row["due_at"]), row["memo_id"]))
    return rows
