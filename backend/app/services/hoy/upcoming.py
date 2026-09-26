"""Próximas: C04 commitments due from tomorrow on, in the rep's zone. No I/O."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_DAYS = 7
MIN_DAYS = 1
MAX_DAYS = 14
MEMO_WINDOW = timedelta(days=60)
MEMO_LIMIT = 500
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


def parse_at(value) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _clean(value) -> str | None:
    text = " ".join(str(value or "").split())
    return text or None


def _extraction(memo: dict) -> dict:
    extraction = memo.get("extraction")
    return extraction if isinstance(extraction, dict) else {}


def _newest_per_contact(memos: list[dict]) -> list[dict]:
    """Hoy's rule (signals_for_contact): only a contact's newest conversation speaks for it."""
    newest: dict[str, tuple[datetime, dict]] = {}
    for memo in memos:
        at = parse_at(memo.get("capture_started_at") or memo.get("created_at"))
        if at is None:
            continue
        key = str(memo.get("hubspot_contact_id") or memo.get("id") or "")
        if key not in newest or at > newest[key][0]:
            newest[key] = (at, memo)
    return [memo for _, memo in newest.values()]


def _names_by_contact(memos: list[dict]) -> dict[str, tuple[str | None, str | None]]:
    names: dict[str, tuple[str | None, str | None]] = {}
    for memo in memos:
        extraction = _extraction(memo)
        name = _clean(extraction.get("contactName"))
        contact = memo.get("hubspot_contact_id")
        if contact and name:
            names[str(contact)] = (name, _clean(extraction.get("companyName")))
    return names


def upcoming_commitments(memos: list[dict], *, now: datetime, tz_name: str | None, days: int = DEFAULT_DAYS) -> list[dict]:
    """Due in [tomorrow 00:00, tomorrow + days 00:00) local. Today and overdue stay on Hoy."""
    start = local_midnight(now, tz_name, days=1)
    end = local_midnight(now, tz_name, days=1 + days)
    names = _names_by_contact(memos)
    seen: set[tuple] = set()
    found: list[tuple[datetime, str, dict]] = []
    for memo in _newest_per_contact(memos):
        extraction = _extraction(memo)
        intelligence = extraction.get("intelligence") if isinstance(extraction.get("intelligence"), dict) else {}
        if intelligence.get("deal_closed") is True:
            continue
        memo_id = str(memo.get("id") or "")
        contact_id = str(memo["hubspot_contact_id"]) if memo.get("hubspot_contact_id") else None
        name, company = _clean(extraction.get("contactName")), _clean(extraction.get("companyName"))
        if not name and contact_id:
            name, company = names.get(contact_id, (None, company))
        for item in intelligence.get("commitments") or []:
            if not isinstance(item, dict) or not _clean(item.get("text")):
                continue
            due = parse_at(item.get("due_at"))
            if due is None or not start <= due < end:
                continue
            key = (memo_id, item.get("id") or (item.get("kind"), due.isoformat(), _clean(item.get("text"))))
            if key in seen:
                continue
            seen.add(key)
            found.append((due, memo_id, {
                "memo_id": memo_id,
                "contact_id": contact_id,
                "contact_name": name,
                "company_name": company,
                "text": _clean(item.get("text")),
                "due_at": due.isoformat(),
                "precision": item.get("temporal_precision") or item.get("precision") or None,
                "crm_task_id": item.get("crm_task_id") or None,
            }))
    found.sort(key=lambda entry: (entry[0], entry[1]))
    return [row for _, _, row in found]
