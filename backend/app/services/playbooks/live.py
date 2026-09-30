"""What applies to a call, in one place.

A playbook applies to a call when it has a published version, is switched on and is not deleted:
`active_version_id IS NOT NULL AND state = 'active' AND archived_at IS NULL`. That rule lives in the SQL view
`playbooks_live` (migration 066_playbooks_v2) and every reader outside `services/playbooks/` goes through this
module, so pausing or deleting a playbook is ignored by the pin on a new call, routing, the copilot, briefs,
coaching and insights without any of them knowing about `state` or `archived_at`.

Two kinds of reads live here, named apart on purpose:
  * live_*    "what applies now": the view.
  * pinned_*  "the version a call was evaluated with": an explicit published version id, whatever the playbook's
              switch says now (a call keeps the version it started with, paused or deleted or replaced).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.services.playbooks.versions import snapshot_view

logger = logging.getLogger(__name__)

LIVE_VIEW = "playbooks_live"
_VERSION_COLS = "id,playbook_id,status,steps,entries,qualification"


def live_versions(supabase: Any, company_id: str, sales_motion_key: Optional[str] = None) -> list[dict]:
    """[{playbook_id, sales_motion_key, version_id}] of the company's live playbooks (of one type when
    `sales_motion_key` is given). Raises when the read fails."""
    query = supabase.table(LIVE_VIEW).select("playbook_id,sales_motion_key,version_id").eq("company_id", company_id)
    if sales_motion_key:
        query = query.eq("sales_motion_key", sales_motion_key)
    rows = [row for row in (getattr(query.execute(), "data", None) or []) if row.get("version_id")]
    return sorted(rows, key=lambda row: str(row.get("sales_motion_key") or ""))


def live_version_id(supabase: Any, company_id: str, sales_motion_key: Optional[str]) -> Optional[str]:
    """The published version that applies to a new call of this type, None when the type has none, is paused or is
    deleted. Never raises: a call is never blocked by a failed read (it gets no version)."""
    if not sales_motion_key:
        return None
    try:
        result = (
            supabase.table(LIVE_VIEW)
            .select("version_id")
            .eq("company_id", company_id)
            .eq("sales_motion_key", sales_motion_key)
            .limit(1)
            .execute()
        )
    except Exception:
        logger.warning("live playbook read failed", extra={"company_id": company_id}, exc_info=True)
        return None
    rows = list(getattr(result, "data", None) or [])
    return (rows[0].get("version_id") or None) if rows else None


def has_published_playbook(supabase: Any, company_id: str) -> bool:
    """Whether the company has a published playbook at all, switched on or paused (a deleted one does not count).
    This is "does the company have a playbook", not "what applies to a call": use live_* for that. Raises when the
    read fails."""
    rows = (
        supabase.table("playbooks")
        .select("id,active_version_id,archived_at")
        .eq("company_id", company_id)
        .execute()
    ).data or []
    return any(row.get("active_version_id") and not row.get("archived_at") for row in rows)


def _published_by_id(supabase: Any, version_ids: list[str]) -> dict[str, dict]:
    if not version_ids:
        return {}
    rows = (
        supabase.table("playbook_versions")
        .select(_VERSION_COLS)
        .in_("id", version_ids)
        .execute()
    ).data or []
    return {str(row["id"]): row for row in rows if row.get("status") == "published"}


def live_snapshots(supabase: Any, company_id: str, sales_motion_key: Optional[str] = None) -> list[dict]:
    """The published content of every live playbook (of one type when `sales_motion_key` is given): [{playbook_id,
    version_id, sales_motion_key, steps, entries, qualification}]. Two reads however many playbooks there are.
    Raises when a read fails."""
    live = live_versions(supabase, company_id, sales_motion_key)
    versions = _published_by_id(supabase, [str(row["version_id"]) for row in live])
    return [
        snapshot_view(row["playbook_id"], row["sales_motion_key"], versions[str(row["version_id"])])
        for row in live
        if str(row["version_id"]) in versions
    ]


def live_snapshot(supabase: Any, company_id: str, sales_motion_key: str) -> Optional[dict]:
    """The published content of this type when it is live, else None. Raises when a read fails."""
    return next(iter(live_snapshots(supabase, company_id, sales_motion_key)), None)


def pinned_snapshot(supabase: Any, company_id: str, sales_motion_key: str, version_id: str) -> Optional[dict]:
    """The published version a call was pinned to (`version_id`), of this type, whether or not the playbook is live
    now. None when it is not a published version of that playbook. Raises when a read fails."""
    playbooks = (
        supabase.table("playbooks")
        .select("id,sales_motion_key")
        .eq("company_id", company_id)
        .eq("sales_motion_key", sales_motion_key)
        .limit(1)
        .execute()
    ).data or []
    if not playbooks:
        return None
    playbook = playbooks[0]
    rows = (
        supabase.table("playbook_versions")
        .select(_VERSION_COLS)
        .eq("playbook_id", playbook["id"])
        .eq("id", version_id)
        .execute()
    ).data or []
    match = next((row for row in rows if str(row.get("id")) == str(version_id) and row.get("status") == "published"), None)
    return snapshot_view(playbook["id"], playbook["sales_motion_key"], match) if match else None
