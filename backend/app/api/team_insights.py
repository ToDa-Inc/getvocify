"""Team reads. A member is rejected before any number is returned."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from app.deps import get_membership
from app.services.company import Membership
from app.services.team_insights.aggregate import TeamAccessError, team_adherence

router = APIRouter(prefix="/api/v1/team", tags=["team"])


@router.get("/adherence")
async def get_team_adherence(membership: Membership = Depends(get_membership)):
    try:
        body = team_adherence(
            role=membership.role,
            parts=[],
            playbook_present=False,
            sample_size=0,
        )
    except TeamAccessError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No puedes ver el equipo") from error
    return JSONResponse(body)
