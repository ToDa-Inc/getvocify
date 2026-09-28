"""GET a stored score. This route does not recompute it."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse

from app.deps import get_membership, get_supabase
from app.services.coaching.best import FLAG as PLAYBOOK_TAB_FLAG, best_by_flow
from app.services.coaching.brief_preferences import highlight_at, read_preference
from app.services.coaching.briefs import absent_brief
from app.services.company import Membership
from app.services.feature_flags import is_enabled
from app.services.team_insights.aggregate import load_team_reps, madrid_week_bounds

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


def _best_week_bounds(week: Optional[str]) -> tuple[datetime, datetime]:
    if not week:
        return madrid_week_bounds()
    try:
        parsed = _parse_instant(week)
    except ValueError:
        return madrid_week_bounds()
    return madrid_week_bounds(now=parsed)


def _load_best_rows(supabase, company_id: str, *, start: datetime, end: datetime) -> list[dict]:
    """Scored memos created in [start, end), for `best_by_flow` to rank and filter.

    `created_at` (not `capture_started_at`) bounds the DB query, matching the rest of the
    codebase's date filters; `best_by_flow` still checks its own instant per row, so a
    memo whose only date is `capture_started_at` is not silently dropped."""
    reps = load_team_reps(supabase, company_id)
    names = {rep["userId"]: rep["name"] for rep in reps}
    member_ids = list(names.keys())
    start_iso = start.isoformat()
    end_iso = end.isoformat()
    try:
        query = (
            supabase.table("memos")
            .select("id,user_id,company_id,sales_motion_key,extraction,capture_started_at,created_at")
            .gte("created_at", start_iso)
            .lt("created_at", end_iso)
        )
        if member_ids:
            query = query.in_("user_id", member_ids).or_(
                f"company_id.eq.{company_id},company_id.is.null"
            )
        else:
            query = query.eq("company_id", company_id)
        memo_rows = list(query.execute().data or [])
    except Exception:
        return []
    memo_ids = [str(memo.get("id")) for memo in memo_rows if memo.get("id")]
    scores_by_memo: dict[str, dict] = {}
    if memo_ids:
        try:
            scored = (
                supabase.table("memo_scores")
                .select("memo_id,score,revision_seq")
                .in_("memo_id", memo_ids)
                .execute()
            )
            for item in scored.data or []:
                memo_id = str(item.get("memo_id"))
                seq = item.get("revision_seq") or 0
                current = scores_by_memo.get(memo_id)
                if current is None or seq >= current["revision_seq"]:
                    scores_by_memo[memo_id] = {"score": item.get("score") or {}, "revision_seq": seq}
        except Exception:
            scores_by_memo = {}
    rows: list[dict] = []
    for memo in memo_rows:
        memo_id = str(memo.get("id"))
        stored = scores_by_memo.get(memo_id)
        if not stored:
            continue
        score = stored["score"] if isinstance(stored["score"], dict) else {}
        extraction = memo.get("extraction") if isinstance(memo.get("extraction"), dict) else {}
        intelligence = extraction.get("intelligence") if isinstance(extraction.get("intelligence"), dict) else {}
        user_id = str(memo.get("user_id") or "")
        rows.append({
            "memo_id": memo_id,
            "user_id": user_id,
            "author": names.get(user_id, ""),
            "sales_motion_key": memo.get("sales_motion_key"),
            "observed_at": memo.get("capture_started_at") or memo.get("created_at"),
            "value": score.get("value"),
            "evidence": intelligence.get("evidence") or [],
        })
    return rows


@router.get("/coaching/best")
async def get_coaching_best(
    week: Optional[str] = Query(None),
    membership: Membership = Depends(get_membership),
    supabase=Depends(get_supabase),
):
    """T11: the week's top 3 interactions per flow. Every company member can read this;
    whether they can open a listed memo is still decided by the memo's own visibility."""
    if not is_enabled(supabase, membership.company_id, PLAYBOOK_TAB_FLAG):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    start, end = _best_week_bounds(week)
    rows = _load_best_rows(supabase, membership.company_id, start=start, end=end)
    body = best_by_flow(rows, start=start, end=end)
    return JSONResponse(body)
