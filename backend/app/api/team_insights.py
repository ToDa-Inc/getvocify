"""Team reads. A member is rejected before any number is returned."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse

from app.deps import get_membership, get_supabase
from app.services.company import Membership
from app.services.feature_flags import is_enabled
from app.services.team_insights.adherence_trend import DEFAULT_WEEKS, FLAG as TREND_FLAG, adherence_trend
from app.services.team_insights.aggregate import TeamAccessError, load_team_adherence_inputs, team_adherence

router = APIRouter(prefix="/api/v1/team", tags=["team"])

_LOADER = None


def set_team_adherence_loader(loader) -> None:
    """loader(supabase, company_id, user_id, motion) -> kwargs for team_adherence."""
    global _LOADER
    _LOADER = loader


def _trend_now() -> datetime:
    return datetime.now(timezone.utc)


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


@router.get("/adherence/trend")
async def get_team_adherence_trend(
    weeks: int = Query(DEFAULT_WEEKS),
    user_id: Optional[str] = Query(None),
    motion: Optional[str] = Query(None),
    membership: Membership = Depends(get_membership),
    supabase=Depends(get_supabase),
):
    # Off means the route does not exist for this company: same body as an unknown path.
    if not is_enabled(supabase, membership.company_id, TREND_FLAG):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    try:
        body = adherence_trend(
            supabase,
            membership.company_id,
            role=membership.role,
            weeks=weeks,
            now=_trend_now(),
            user_id=user_id,
            motion=motion,
        )
    except TeamAccessError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No puedes ver el equipo") from error
    return JSONResponse(body)
