"""Analysis of captured conversations: how much is read, and a way to read the rest."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from app.deps import get_membership, get_supabase
from app.services.activity_scope import can_view_company_activity
from app.services.company import CompanyService, Membership
from app.services.intelligence import backfill

router = APIRouter(prefix="/api/v1/intelligence", tags=["intelligence"])


def _members(supabase, company_id: str) -> list[str]:
    return [
        str(m["user_id"])
        for m in CompanyService(supabase).list_members(company_id)
        if m.get("user_id") and (m.get("status") or "active") == "active"
    ]


@router.get("/coverage")
async def get_coverage(membership: Membership = Depends(get_membership), supabase=Depends(get_supabase)):
    """Owners and admins see the company; a member sees their own conversations."""
    ids = _members(supabase, membership.company_id) if can_view_company_activity(membership.role) else [membership.user_id]
    return {**backfill.coverage(supabase, membership.company_id, ids), **backfill.progress(membership.company_id)}


@router.post("/backfill")
async def start_backfill(membership: Membership = Depends(get_membership), supabase=Depends(get_supabase)):
    if not can_view_company_activity(membership.role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo owners y admins pueden analizar el historial")
    result = backfill.start_backfill(supabase, membership.company_id, _members(supabase, membership.company_id))
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=result)
