"""Team reads. A member is rejected before any number is returned."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from app.deps import get_membership, get_supabase
from app.services.company import Membership
from app.services.team_insights.aggregate import TeamAccessError, load_team_adherence_inputs, team_adherence

router = APIRouter(prefix="/api/v1/team", tags=["team"])

_LOADER = None


def set_team_adherence_loader(loader) -> None:
    """loader(supabase, company_id) -> kwargs for team_adherence. None reads memos and scores."""
    global _LOADER
    _LOADER = loader


@router.get("/adherence")
async def get_team_adherence(
    membership: Membership = Depends(get_membership),
    supabase=Depends(get_supabase),
):
    try:
        if _LOADER is not None:
            inputs = _LOADER(supabase, membership.company_id)
        else:
            inputs = load_team_adherence_inputs(supabase, membership.company_id)
        body = team_adherence(role=membership.role, **inputs)
    except TeamAccessError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No puedes ver el equipo") from error
    return JSONResponse(body)
