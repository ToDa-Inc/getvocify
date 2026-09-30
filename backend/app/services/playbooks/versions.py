"""Playbook version rules that need no database: who can publish, the errors, timestamps, and a published snapshot by id.
A meeting keeps the version it started with."""

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


class LifecycleError(Exception):
    """Pause, resume, delete or restore does not apply to the type as it is. `code` is what the
    API answers: not_published (pause), not_paused (resume), not_archived (restore), not_found
    (delete of a type the company does not have)."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


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
    """Publish one draft. A member is refused, and any other typology stays as it was. A paused
    playbook can be published too (a pending draft goes live and lifts the pause): whether it has
    a draft is the store's call, its status only says "paused"."""
    if not can_publish(role):
        raise PublishError("forbidden")
    if motions.get(key) not in ("draft", "paused"):
        raise PublishError("not_a_draft")
    updated = dict(motions)
    updated[key] = "published"
    return updated


def snapshot_for_capture(pinned_version_id: Optional[str], live_version_id: Optional[str]) -> Optional[str]:
    """The version a new capture is pinned to: the one the caller named, else the live one."""
    return pinned_version_id or live_version_id


def published_snapshot(playbook: Optional[dict], versions: list[dict], version_id: str) -> Optional[dict]:
    """The published snapshot with this id, of this playbook ({id, sales_motion_key, ...}), None when it is not one.
    For a version a call was pinned to; what applies to a NEW call is decided by services/playbooks/live.py."""
    if not playbook or not version_id:
        return None
    match = next((row for row in versions if row["id"] == version_id), None)
    if not match or match.get("status") != "published":
        return None
    return snapshot_view(playbook["id"], playbook["sales_motion_key"], match)


def validate_entries(entries: list[dict]) -> None:
    for entry in entries:
        if not (entry.get("source_ref") or "").strip():
            raise ValueError("una entrada sin fuente no se publica")


def snapshot_view(playbook_id: str, sales_motion_key: str, version: dict) -> dict:
    """A published version row as every consumer reads it."""
    return {
        "playbook_id": playbook_id,
        "version_id": version["id"],
        "sales_motion_key": sales_motion_key,
        "steps": version.get("steps") or [],
        "entries": version.get("entries") or [],
        "qualification": version.get("qualification") or [],
    }
