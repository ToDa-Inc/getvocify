"""Published playbook snapshots. A meeting keeps the version it started with."""

from __future__ import annotations

from typing import Optional


def can_publish(role: str) -> bool:
    return role in {"owner", "admin"}


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
