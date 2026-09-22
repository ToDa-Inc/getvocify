"""GET a stored score. This route does not recompute it."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.deps import get_membership, get_supabase
from app.services.company import Membership

router = APIRouter(prefix="/api/v1", tags=["coaching"])


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
