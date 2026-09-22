"""Hoy actions. The same request returns the same transition. Undo does not touch a call or an email."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


UNDO_WINDOW = timedelta(seconds=5)
_STATUS = {"resolve": "resolved", "dismiss": "dismissed", "snooze": "snoozed"}


class ActionError(Exception):
    def __init__(self, code: str, row: dict):
        self.code = code
        self.row = row


def apply_action(
    row: dict,
    *,
    action: str,
    request_id: str,
    expected_version: int,
    until: datetime | None,
    now: datetime,
    user_id: str,
    company_id: str,
) -> dict:
    _owned(row, user_id=user_id, company_id=company_id)
    if row.get("last_action_request_id") == request_id:
        return {**row, "replayed": True}
    if row.get("version") != expected_version:
        raise ActionError("conflict", row)
    if action not in _STATUS:
        raise ActionError("invalid", row)
    if action == "snooze" and (until is None or until <= now):
        raise ActionError("invalid", row)
    deadline = now + UNDO_WINDOW
    return {
        **row,
        "previous_status": row.get("status"),
        "status": _STATUS[action],
        "version": row["version"] + 1,
        "last_action_request_id": request_id,
        "last_action_at": _iso(now),
        "undo_deadline": _iso(deadline),
        "snoozed_until": _iso(until) if action == "snooze" else None,
        "replayed": False,
    }


def undo_action(
    row: dict,
    *,
    request_id: str,
    expected_version: int,
    now: datetime,
    user_id: str,
    company_id: str,
) -> dict:
    """Restore the signal only. A call and a sent email stay as they were."""
    _owned(row, user_id=user_id, company_id=company_id)
    if row.get("version") != expected_version or row.get("last_action_request_id") != request_id:
        raise ActionError("conflict", row)
    deadline = _parse(row.get("undo_deadline"))
    if deadline is None or now > deadline:
        raise ActionError("expired", row)
    return {
        **row,
        "status": row.get("previous_status") or "pending",
        "previous_status": row.get("status"),
        "version": row["version"] + 1,
        "undo_deadline": None,
        "snoozed_until": None,
        "replayed": False,
    }


def _owned(row: dict, *, user_id: str, company_id: str) -> None:
    if row.get("company_id") != company_id or row.get("user_id") != user_id:
        raise ActionError("forbidden", row)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _parse(value):
    if value is None or isinstance(value, datetime):
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
