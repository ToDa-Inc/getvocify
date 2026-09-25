"""Team reads. A member is rejected before any number is returned."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse

from app.deps import get_membership, get_supabase
from app.services.company import Membership
from app.services.team_insights.aggregate import TeamAccessError, load_team_adherence_inputs, team_adherence

router = APIRouter(prefix="/api/v1/team", tags=["team"])

_LOADER = None


def set_team_adherence_loader(loader) -> None:
    """loader(supabase, company_id, user_id, motion) -> kwargs for team_adherence."""
    global _LOADER
    _LOADER = loader


@router.get("/adherence")
async def get_team_adherence(
    user_id: Optional[str] = Query(None),
    motion: Optional[str] = Query(None),
    membership: Membership = Depends(get_membership),
    supabase=Depends(get_supabase),
):
    try:
        if _LOADER is not None:
            inputs = _LOADER(supabase, membership.company_id, user_id, motion)
        else:
            inputs = load_team_adherence_inputs(
                supabase,
                membership.company_id,
                user_id=user_id,
                motion=motion,
            )
        body = team_adherence(role=membership.role, **inputs)
    except TeamAccessError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No puedes ver el equipo") from error
    return JSONResponse(body)
