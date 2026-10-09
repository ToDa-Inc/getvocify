"""GET/PUT brief highlight preference for the signed-in user."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.deps import get_membership
from app.services.company import Membership
from app.services.coaching.brief_preferences import read_preference, write_preference

router = APIRouter(prefix="/api/v1", tags=["brief-preferences"])


class BriefPreferenceBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    highlight_mode: str
    delay_minutes: int | None = None
    end_of_day: str | None = None
    timezone: str | None = Field(default=None)


@router.get("/brief-preferences")
async def get_brief_preferences(membership: Membership = Depends(get_membership)):
    return read_preference(membership.user_id)


@router.put("/brief-preferences")
async def put_brief_preferences(
    body: BriefPreferenceBody,
    membership: Membership = Depends(get_membership),
):
    try:
        return write_preference(
            membership.user_id,
            body.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
