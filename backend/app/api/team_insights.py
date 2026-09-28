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
from app.services.coaching.best import FLAG as PLAYBOOK_TAB_FLAG
from app.services.team_insights.competitors import COMPETITORS_FLAG
from app.services.team_insights.aggregate import TeamAccessError, assert_team_reader, load_team_adherence_inputs, team_adherence
from app.services.team_insights.rep_detail import rep_handoffs, rep_sales_role

router = APIRouter(prefix="/api/v1/team", tags=["team"])

# T13: /dashboard becomes the Head of Sales' team home, with a per-rep detail page.
MANAGER_HOME_FLAG = "MANAGER_HOME_ENABLED"
HANDOFF_FLAG = "HANDOFF_ENABLED"

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
        # T11: how_to/best_example only when the Playbook tab is on for this company —
        # off keeps the objection_categories items in the pre-T11 shape.
        include_guidance = is_enabled(supabase, membership.company_id, PLAYBOOK_TAB_FLAG)
        body = team_adherence(
            role=membership.role,
            visibility=membership.visibility,
            include_objection_guidance=include_guidance,
            **inputs,
        )
    except TeamAccessError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No puedes ver el equipo") from error
    if not is_enabled(supabase, membership.company_id, COMPETITORS_FLAG):
        body.pop("competitor_mentions", None)
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
            visibility=membership.visibility,
        )
    except TeamAccessError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No puedes ver el equipo") from error
    return JSONResponse(body)


@router.get("/rep/{user_id}")
async def get_team_rep_detail(
    user_id: str,
    membership: Membership = Depends(get_membership),
    supabase=Depends(get_supabase),
):
    """T13: what the per-rep detail page needs beyond /team/adherence?user_id= and
    /team/adherence/trend?user_id= (both already generic) - the rep's own sales_role and
    its handoffs, SDR past / AE received."""
    if not is_enabled(supabase, membership.company_id, MANAGER_HOME_FLAG):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    try:
        assert_team_reader(membership.role, membership.visibility)
    except TeamAccessError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No puedes ver el equipo") from error
    sales_role = rep_sales_role(supabase, company_id=membership.company_id, user_id=user_id)
    handoffs = None
    if is_enabled(supabase, membership.company_id, HANDOFF_FLAG):
        handoffs = rep_handoffs(supabase, company_id=membership.company_id, user_id=user_id)
    return JSONResponse({"user_id": user_id, "sales_role": sales_role, "handoffs": handoffs})
