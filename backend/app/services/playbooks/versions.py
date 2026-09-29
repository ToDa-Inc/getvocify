"""Published playbook snapshots. A meeting keeps the version it started with."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional


def can_publish(role: str) -> bool:
    return role in {"owner", "admin"}


class PublishError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class StaleDraftError(Exception):
    """The draft was changed (saved, published or discarded) by someone else since the
    caller loaded it: its `base_updated_at` no longer matches. The API answers 409
    `stale_draft`; the editor offers a reload instead of overwriting."""

    code = "stale_draft"

    def __init__(self) -> None:
        super().__init__("stale_draft")


_FRACTION = re.compile(r"\.(\d+)")


def parse_ts(value: Any) -> Optional[datetime]:
    """An ISO timestamp (Postgres `+00:00`, JS `Z`, any number of fraction digits, or a
    datetime) as an aware UTC datetime; None when it is empty or unreadable. Timestamps
    are compared as instants, never as strings: Supabase and a browser spell the same
    moment differently."""
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        if not text:
            return None
        text = text.replace(" ", "T", 1) if "T" not in text else text
        if text.endswith(("Z", "z")):
            text = text[:-1] + "+00:00"
        text = _FRACTION.sub(lambda m: "." + (m.group(1) + "000000")[:6], text, count=1)
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def same_instant(a: Any, b: Any) -> bool:
    """Whether two timestamps name the same moment, to the millisecond (a client that
    round-trips the value through a JS Date loses the microseconds). Unparsable values
    fall back to string equality."""
    left, right = parse_ts(a), parse_ts(b)
    if left is None or right is None:
        return str(a or "") == str(b or "")
    return left.replace(microsecond=left.microsecond // 1000 * 1000) == right.replace(
        microsecond=right.microsecond // 1000 * 1000
    )


def is_newer(a: Any, b: Any) -> bool:
    """a > b as instants. A missing `b` is older than anything; a missing `a` is not newer."""
    left, right = parse_ts(a), parse_ts(b)
    if left is None:
        return False
    if right is None:
        return True
    return left > right


def accept_publish(motions: dict, key: str, role: str) -> dict:
    """Publish one draft. A member is refused, and any other typology stays as it was."""
    if not can_publish(role):
        raise PublishError("forbidden")
    if motions.get(key) != "draft":
        raise PublishError("not_a_draft")
    updated = dict(motions)
    updated[key] = "published"
    return updated


def snapshot_for_capture(pinned_version_id: Optional[str], active_version_id: Optional[str]) -> Optional[str]:
    return pinned_version_id or active_version_id


def get_published_playbook(playbook: Optional[dict], versions: list[dict], version_id: Optional[str] = None) -> Optional[dict]:
    """Return a published snapshot, or None when the company has not published one."""
    if not playbook:
        return None
    if version_id:
        match = next((row for row in versions if row["id"] == version_id), None)
        if not match or match.get("status") != "published":
            return None
        return _view(playbook, match)
    active = playbook.get("active_version_id")
    if not active:
        return None
    match = next((row for row in versions if row["id"] == active and row.get("status") == "published"), None)
    if not match:
        return None
    return _view(playbook, match)


def validate_entries(entries: list[dict]) -> None:
    for entry in entries:
        if not (entry.get("source_ref") or "").strip():
            raise ValueError("una entrada sin fuente no se publica")


def _view(playbook: dict, version: dict) -> dict:
    return {
        "playbook_id": playbook["id"],
        "version_id": version["id"],
        "sales_motion_key": playbook["sales_motion_key"],
        "steps": version.get("steps") or [],
        "entries": version.get("entries") or [],
    }
