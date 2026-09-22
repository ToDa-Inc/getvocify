"""GET the stored meeting proposal. POST accept / omit / correct."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.deps import get_membership, get_supabase
from app.models.meetings import MeetingProposalAcceptRequest
from app.services.company import Membership
from app.services.meetings.accept import WriterFactory, accept_meeting_proposal
from app.services.meetings.proposals import latest_proposal

router = APIRouter(prefix="/api/v1", tags=["meetings"])

_WRITER_FACTORY: WriterFactory | None = None


def set_meeting_writer_factory(factory: WriterFactory | None) -> None:
    global _WRITER_FACTORY
    _WRITER_FACTORY = factory


@router.get("/memos/{memo_id}/meeting-proposal")
async def get_meeting_proposal(
    memo_id: str,
    membership: Membership = Depends(get_membership),
    supabase=Depends(get_supabase),
):
    try:
        memo = (
            supabase.table("memos")
            .select("id,company_id")
            .eq("id", memo_id)
            .execute()
        )
        rows = (
            supabase.table("meeting_proposals")
            .select("*")
            .eq("memo_id", memo_id)
            .execute()
        )
    except Exception:
        return {"proposal": None}
    found = memo.data or []
    if not found or found[0].get("company_id") != membership.company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memo no encontrado")
    return {"proposal": latest_proposal(rows.data or [])}


@router.post("/memos/{memo_id}/meeting-proposal/accept")
async def accept_meeting_proposal_route(
    memo_id: str,
    payload: MeetingProposalAcceptRequest,
    membership: Membership = Depends(get_membership),
    supabase=Depends(get_supabase),
):
    return accept_meeting_proposal(
        supabase,
        company_id=membership.company_id,
        memo_id=memo_id,
        decision=payload.decision,
        proposal_id=payload.proposal_id,
        starts_at=payload.starts_at,
        writer_factory=_WRITER_FACTORY,
    )
