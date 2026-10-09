"""What Vocify did on its own, read from the audit rows that already exist. No copy, no invented dates."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

WINDOW_DAYS = 7
MAX_ITEMS = 8
RESOURCE_ORDER = ("deal", "contact", "company", "task", "note", "line_item")


def _instant(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _subject(memo: dict) -> str | None:
    extraction = memo.get("extraction") if isinstance(memo.get("extraction"), dict) else {}
    for key in ("contactName", "companyName"):
        text = str((extraction or {}).get(key) or "").strip()
        if text:
            return text
    return None


def _own_memo(memo: dict | None, *, user_id: str, company_id: str) -> bool:
    if not memo or str(memo.get("user_id")) != str(user_id):
        return False
    memo_company = memo.get("company_id")
    return memo_company is None or str(memo_company) == str(company_id)


def vocify_activity(
    update_rows: list[dict],
    meeting_rows: list[dict],
    memos_by_id: dict[str, dict],
    *,
    user_id: str,
    company_id: str,
    now: datetime,
) -> list[dict]:
    """Successful CRM writes grouped by conversation, and meeting stage moves with a known date."""
    since = now - timedelta(days=WINDOW_DAYS)
    groups: dict[str, dict] = {}
    for row in update_rows:
        if row.get("status") != "success" or str(row.get("user_id")) != str(user_id):
            continue
        memo_id = str(row.get("memo_id") or "")
        memo = memos_by_id.get(memo_id)
        if not _own_memo(memo, user_id=user_id, company_id=company_id):
            continue
        at = _instant(row.get("completed_at") or row.get("created_at"))
        if at is None or at < since:
            continue
        group = groups.setdefault(memo_id, {"at": at, "resources": set(), "memo": memo})
        group["at"] = max(group["at"], at)
        if row.get("resource_type"):
            group["resources"].add(str(row["resource_type"]))
    items: list[tuple[datetime, dict]] = [
        (
            group["at"],
            {
                "kind": "crm_updated",
                "memo_id": memo_id,
                "subject": _subject(group["memo"]),
                "resources": [name for name in RESOURCE_ORDER if name in group["resources"]],
                "at": group["at"].isoformat(),
            },
        )
        for memo_id, group in groups.items()
    ]
    for row in meeting_rows:
        if row.get("stage_changed") is not True:
            continue
        at = _instant(row.get("created_at"))
        if at is None or at < since:
            continue
        memo_id = str(row.get("memo_id") or "")
        memo = memos_by_id.get(memo_id)
        if not _own_memo(memo, user_id=user_id, company_id=company_id):
            continue
        items.append((
            at,
            {"kind": "meeting_stage", "memo_id": memo_id, "subject": _subject(memo), "resources": [], "at": at.isoformat()},
        ))
    items.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in items[:MAX_ITEMS]]


def load_vocify_activity(supabase, *, user_id: str, company_id: str, now: datetime) -> list[dict] | None:
    """None when a source cannot be read: an unread audit is not "nothing happened"."""
    since = (now - timedelta(days=WINDOW_DAYS)).isoformat()
    try:
        updates = (
            supabase.table("crm_updates")
            .select("memo_id,user_id,action_type,resource_type,status,created_at,completed_at")
            .eq("user_id", user_id)
            .eq("status", "success")
            .gte("created_at", since)
            .execute()
        ).data or []
        writes = (
            supabase.table("meeting_writes")
            .select("memo_id,stage_changed,crm_status,created_at")
            .eq("stage_changed", True)
            .gte("created_at", since)
            .execute()
        ).data or []
        memo_ids = sorted({str(row["memo_id"]) for row in [*updates, *writes] if row.get("memo_id")})
        memos: list[dict] = []
        if memo_ids:
            memos = (
                supabase.table("memos")
                .select("id,user_id,company_id,extraction")
                .in_("id", memo_ids)
                .execute()
            ).data or []
    except Exception:
        logger.exception("bell activity: read failed")
        return None
    by_id = {str(memo["id"]): memo for memo in memos if memo.get("id")}
    return vocify_activity(updates, writes, by_id, user_id=user_id, company_id=company_id, now=now)
