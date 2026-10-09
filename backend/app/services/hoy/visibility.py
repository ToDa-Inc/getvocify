"""Which stored signals appear on GET /today."""

from __future__ import annotations

from datetime import datetime, timezone


def _parse(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def is_today_visible(row: dict, now: datetime) -> bool:
    status = row.get("status")
    if status == "pending":
        return True
    if status == "dismissed":
        deadline = _parse(row.get("undo_deadline"))
        return deadline is not None and now <= deadline
    return False
