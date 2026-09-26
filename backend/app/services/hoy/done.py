"""Hecho hoy: what the rep finished since local midnight. No I/O."""

from __future__ import annotations

from datetime import datetime

from app.services.hoy.upcoming import local_midnight, parse_at

LIMIT = 50
SIGNAL_DONE = frozenset({"resolved", "done"})
CALL_DONE = frozenset({"connected"})

Names = tuple[dict[str, tuple[str | None, str | None]], dict[str, tuple[str | None, str | None]]]


def _name(names: Names, memo_id, contact_id) -> str | None:
    by_memo, by_contact = names
    found = by_memo.get(str(memo_id)) if memo_id else None
    if found and found[0]:
        return found[0]
    found = by_contact.get(str(contact_id)) if contact_id else None
    return found[0] if found else None


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
        at = parse_at(value)
        return at if at is not None and start <= at <= now else None

    found: list[tuple[datetime, dict]] = []
    for row in signals:
        at = today(row.get("last_action_at"))
        if at is None or not _signal_done_by_rep(row):
            continue
        memo_id = row.get("memo_id") or None
        found.append((at, {
            "kind": "signal",
            "contact_name": _name(names, memo_id, row.get("contact_id")),
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
            "at": at.isoformat(),
            "memo_id": memo.get("id"),
        }))
    for call in calls:
        if today(call.get("created_at")) is None or call.get("call_disposition") not in CALL_DONE:
            continue
        at = parse_at(call.get("answered_at")) or parse_at(call.get("created_at"))
        memo_id = call.get("memo_id") or None
        found.append((at, {
            "kind": "call",
            "contact_name": _name(names, memo_id, call.get("hubspot_contact_id")),
            "at": at.isoformat(),
            "memo_id": memo_id,
        }))
    found.sort(key=lambda entry: entry[0], reverse=True)
    return [row for _, row in found[:limit]]
