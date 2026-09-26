"""Hecho hoy: what the rep finished since local midnight. No I/O."""

from __future__ import annotations

from datetime import datetime

from app.services.hoy.materialize import as_dt
from app.services.hoy.names import NamePair, lookup
from app.services.hoy.upcoming import local_midnight

LIMIT = 50
SIGNAL_DONE = frozenset({"resolved", "done"})
CALL_DONE = frozenset({"connected"})

Names = tuple[dict[str, NamePair], dict[str, NamePair]]


def _name(names: Names, memo_id, contact_id) -> str | None:
    return lookup(names, memo_id, contact_id)[0]


def _signal_done_by_rep(row: dict) -> bool:
    """Only the rep's resolve writes status and last_action_at together.

    Automatic resolves (reply seen, signal stopped applying) leave last_action_at as it was, so an
    earlier undo (undo_deadline cleared) or snooze the same day must not pass for a resolve.
    """
    return (
        row.get("status") in SIGNAL_DONE
        and row.get("undo_deadline") is not None
        and row.get("previous_status") != "snoozed"
    )


def done_today(
    *,
    signals: list[dict],
    followups: list[dict],
    calls: list[dict],
    names: Names,
    now: datetime,
    tz_name: str | None,
    limit: int = LIMIT,
) -> list[dict]:
    start = local_midnight(now, tz_name)

    def today(value) -> datetime | None:
        at = as_dt(value)
        return at if at is not None and start <= at <= now else None

    found: list[tuple[datetime, dict]] = []
    for row in signals:
        at = today(row.get("last_action_at"))
        if at is None or not _signal_done_by_rep(row):
            continue
        memo_id = row.get("memo_id") or None
        kind = "confirmation" if row.get("type") == "confirm_pending" else "signal"
        found.append((at, {
            "kind": kind,
            "contact_name": _name(names, memo_id, row.get("contact_id")),
            "contact_id": row.get("contact_id") or None,
            "at": at.isoformat(),
            "memo_id": memo_id,
        }))
    for memo in followups:
        followup = memo.get("followup") if isinstance(memo.get("followup"), dict) else {}
        at = today(followup.get("sent_at"))
        if at is None or followup.get("status") != "sent":
            continue
        found.append((at, {
            "kind": "followup",
            "contact_name": _name(names, memo.get("id"), memo.get("hubspot_contact_id")),
            "contact_id": memo.get("hubspot_contact_id") or None,
            "at": at.isoformat(),
            "memo_id": memo.get("id"),
        }))
    for call in calls:
        if today(call.get("created_at")) is None or call.get("call_disposition") not in CALL_DONE:
            continue
        at = as_dt(call.get("answered_at")) or as_dt(call.get("created_at"))
        memo_id = call.get("memo_id") or None
        found.append((at, {
            "kind": "call",
            "contact_name": _name(names, memo_id, call.get("hubspot_contact_id")),
            "contact_id": call.get("hubspot_contact_id") or None,
            "at": at.isoformat(),
            "memo_id": memo_id,
        }))
    found.sort(key=lambda entry: entry[0], reverse=True)
    return [row for _, row in found[:limit]]
