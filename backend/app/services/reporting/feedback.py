"""T12 bell "Feedback": ready post-interaction briefs whose highlight time has passed and
that this rep has not opened yet (brief_seen, migration 060). Own memos only - a manager
does not get a rep's brief in their own bell."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.services.coaching.brief_preferences import highlight_at, read_preference

logger = logging.getLogger(__name__)

MAX_FEEDBACK = 8
_WINDOW_DAYS = 14


def _instant(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _ready_at(row: dict) -> datetime | None:
    body = row.get("body") if isinstance(row.get("body"), dict) else {}
    return _instant(body.get("ready_at")) or _instant(row.get("created_at"))


def _latest_per_memo(rows: list[dict]) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for row in rows:
        memo_id = str(row.get("memo_id") or "")
        if not memo_id:
            continue
        current = latest.get(memo_id)
        if current is None or (row.get("revision_seq") or 0) > (current.get("revision_seq") or 0):
            latest[memo_id] = row
    return latest


def unseen_feedback(
    brief_rows: list[dict],
    *,
    seen_memo_ids: set[str],
    now: datetime,
    preference: dict,
) -> list[dict]:
    """Pure: `brief_rows` are this user's own memos' post_interaction_briefs rows."""
    items: list[tuple[datetime, dict]] = []
    for memo_id, row in _latest_per_memo(brief_rows).items():
        if row.get("status") != "ready" or memo_id in seen_memo_ids:
            continue
        ready_at = _ready_at(row)
        if ready_at is None:
            continue
        shown_at = highlight_at(ready_at, preference)
        if shown_at > now:
            continue
        items.append((shown_at, {"memo_id": memo_id, "highlight_at": shown_at.isoformat()}))
    items.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in items[:MAX_FEEDBACK]]


def load_unseen_feedback(supabase, *, user_id: str, company_id: str, now: datetime) -> list[dict] | None:
    """None when a source cannot be read: an unread table is not "nothing to show"."""
    since = (now - timedelta(days=_WINDOW_DAYS)).isoformat()
    try:
        memos = (
            supabase.table("memos")
            .select("id")
            .eq("company_id", company_id)
            .eq("user_id", user_id)
            .gte("created_at", since)
            .execute()
        ).data or []
        memo_ids = [str(row["id"]) for row in memos if row.get("id")]
        briefs: list[dict] = []
        if memo_ids:
            briefs = (
                supabase.table("post_interaction_briefs")
                .select("memo_id,input_revision,revision_seq,status,body,created_at")
                .in_("memo_id", memo_ids)
                .execute()
            ).data or []
        seen: set[str] = set()
        if memo_ids:
            seen_rows = (
                supabase.table("brief_seen")
                .select("memo_id")
                .eq("user_id", user_id)
                .in_("memo_id", memo_ids)
                .execute()
            ).data or []
            seen = {str(row["memo_id"]) for row in seen_rows if row.get("memo_id")}
    except Exception:
        logger.exception("bell feedback: read failed")
        return None
    preference = read_preference(user_id)
    return unseen_feedback(briefs, seen_memo_ids=seen, now=now, preference=preference)


def mark_feedback_seen(supabase, *, user_id: str, memo_id: str, now: datetime) -> None:
    supabase.table("brief_seen").upsert(
        {"user_id": user_id, "memo_id": memo_id, "seen_at": now.isoformat()},
        on_conflict="user_id,memo_id",
    ).execute()
