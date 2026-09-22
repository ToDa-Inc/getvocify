"""GET a stored score. This route does not recompute it."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from app.deps import get_membership, get_supabase
from app.services.coaching.brief_preferences import highlight_at, read_preference
from app.services.coaching.briefs import absent_brief
from app.services.company import Membership

router = APIRouter(prefix="/api/v1", tags=["coaching"])


def _parse_instant(raw: object) -> datetime:
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    text = str(raw).replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _brief_ready_at(row: dict, body: dict) -> datetime:
    if body.get("ready_at"):
        return _parse_instant(body["ready_at"])
    if row.get("created_at"):
        return _parse_instant(row["created_at"])
    return datetime.now(timezone.utc)


def _attach_highlight(body: dict, *, user_id: str, ready_at: datetime) -> dict:
    preference = read_preference(user_id)
    shown = highlight_at(ready_at, preference)
    iso = shown.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        **body,
        "highlight": {
            "highlight_mode": preference["highlight_mode"],
            "highlight_at": iso,
            "timezone": preference["timezone"],
        },
    }


@router.get("/memos/{memo_id}/score")
async def get_memo_score(
    memo_id: str,
    membership: Membership = Depends(get_membership),
    supabase=Depends(get_supabase),
):
    memo = (
        supabase.table("memos")
        .select("id,company_id")
        .eq("id", memo_id)
        .execute()
    )
    rows = memo.data or []
    if not rows or rows[0].get("company_id") != membership.company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memo no encontrado")
    stored = (
        supabase.table("memo_scores")
        .select("*")
        .eq("memo_id", memo_id)
        .execute()
    )
    scores = stored.data or []
    if not scores:
        return {
            "status": "unavailable",
            "value": None,
            "reason": "not_scored",
            "strengths": [],
            "improvements": [],
            "crm_outcome": None,
            "adherence": None,
            "coverage": None,
        }
    current = max(scores, key=lambda row: row.get("revision_seq") or 0)
    body = dict(current.get("score") or {})
    body["playbook_version_id"] = current.get("playbook_version_id")
    return body


@router.get("/memos/{memo_id}/brief")
async def get_memo_brief(
    memo_id: str,
    membership: Membership = Depends(get_membership),
    supabase=Depends(get_supabase),
):
    memo = (
        supabase.table("memos")
        .select("id,company_id")
        .eq("id", memo_id)
        .execute()
    )
    rows = memo.data or []
    if not rows or rows[0].get("company_id") != membership.company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memo no encontrado")
    stored = (
        supabase.table("post_interaction_briefs")
        .select("*")
        .eq("memo_id", memo_id)
        .execute()
    )
    briefs = stored.data or []
    if not briefs:
        return absent_brief()
    current = max(briefs, key=lambda row: row.get("revision_seq") or 0)
    body = dict(current.get("body") or {})
    body["status"] = current.get("status")
    body["input_revision"] = current.get("input_revision")
    ready_at = _brief_ready_at(current, body)
    return _attach_highlight(body, user_id=membership.user_id, ready_at=ready_at)
