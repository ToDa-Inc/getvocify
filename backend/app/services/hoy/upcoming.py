"""Próximas: C04 commitments due from tomorrow on, in the rep's zone - and, with
HOY_SDR_SECTIONS_ENABLED (Lista 4 T2), the follow-ups whose cadence date is still ahead. No I/O."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.services.hoy.cadence import followup_due_at, stopper_for
from app.services.hoy.materialize import (
    _commitments,
    _intelligence,
    as_dt,
    contact_touches,
    fresh_signals,
    handoff_touches,
)
from app.services.hoy.names import clean_name, lookup, memo_directory
from app.services.hoy.reasons import followup_upcoming_text
from app.services.hoy.signals import UNANSWERED_OUTCOMES

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


def upcoming_followups(
    memos: list[dict],
    *,
    now: datetime,
    tz_name: str | None,
    days: int = DEFAULT_DAYS,
    overrides: dict[str, int] | None = None,
    lang: str = "es",
) -> list[dict]:
    """Follow-ups due in [tomorrow 00:00, tomorrow + days 00:00) local: the contacts Hoy is
    deliberately not showing yet, so the rep sees when each comes back. Same rules as
    signals_for_contact's followup_due - the latest touch only; a closed deal, any dated
    commitment (it is a task, listed above on its own date) or an unanswered last call
    (a callback) means no follow-up row."""
    start = local_midnight(now, tz_name, days=1)
    end = local_midnight(now, tz_name, days=1 + days)
    directory = memo_directory(memos)
    groups, _pain = contact_touches(memos)
    rows: list[dict] = []
    for touches in groups.values():
        last = max(touches, key=lambda t: t.at)
        if last.deal_closed or last.commitments or last.screening_outcome in UNANSWERED_OUTCOMES:
            continue
        due = followup_due_at(last, overrides)
        if due is None or not start <= due < end:
            continue
        rows.append(_followup_row(last, due, directory, lang))
    rows.sort(key=lambda row: (as_dt(row["due_at"]), row["memo_id"]))
    return rows


def upcoming_handoff_followups(
    handoffs: list[dict],
    sdr_memos: list[dict],
    *,
    own_contact_ids: set[str],
    now: datetime,
    tz_name: str | None,
    days: int = DEFAULT_DAYS,
    overrides: dict[str, int] | None = None,
    lang: str = "es",
) -> list[dict]:
    """Lista 4 T8 (E13): the AE's handed-off contacts with no AE memo yet, on the date the
    SDR's last conversation's cadence brings them back, counted from the handoff meeting -
    the same rule materialize.handoff_followup_signals uses for Hoy."""
    start = local_midnight(now, tz_name, days=1)
    end = local_midnight(now, tz_name, days=1 + days)
    directory = memo_directory(sdr_memos)
    rows: list[dict] = []
    for _handoff, touch in handoff_touches(handoffs, sdr_memos, own_contact_ids=own_contact_ids):
        due = followup_due_at(touch, overrides)
        if due is None or not start <= due < end:
            continue
        rows.append(_followup_row(touch, due, directory, lang))
    rows.sort(key=lambda row: (as_dt(row["due_at"]), row["memo_id"]))
    return rows


def _followup_row(last, due: datetime, directory, lang: str) -> dict:
    name, company = lookup(directory, last.memo_id, last.contact_id)
    return {
        "memo_id": last.memo_id,
        "contact_id": last.contact_id,
        "contact_name": name,
        "company_name": company,
        "text": followup_upcoming_text(stopper_for(last), lang),
        "due_at": due.isoformat(),
        "precision": "date",
        "crm_task_id": None,
        "kind": "followup",
    }
