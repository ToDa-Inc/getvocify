"""Demo buyer for sales demos (owner/admin only): a scenario per prospect and free replies."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.deps import require_company_role
from app.services import demo_buyer
from app.services.company import Membership

router = APIRouter(prefix="/api/v1/demo", tags=["demo"])

Language = Literal["es", "en"]


class ScenarioRequest(BaseModel):
    offer: str = Field(..., min_length=3, max_length=600)
    niche: str = Field(..., min_length=2, max_length=200)
    company: str | None = Field(default=None, max_length=120)
    prospect_name: str | None = Field(default=None, max_length=80)
    language: Language = "es"
    voice: str | None = Field(default=None, max_length=40)


class Turn(BaseModel):
    role: Literal["buyer", "seller"]
    text: str = Field(..., max_length=1200)


class Persona(BaseModel):
    name: str = Field(..., max_length=120)
    role: str = Field(..., max_length=160)
    company: str = Field(..., max_length=160)
    background: str = Field(..., max_length=600)


class ReplyRequest(BaseModel):
    persona: Persona
    language: Language = "es"
    voice: str = Field(default=demo_buyer.DEFAULT_VOICE, max_length=40)
    history: list[Turn] = Field(default_factory=list, max_length=40)
    seller_text: str = Field(..., min_length=1, max_length=1200)


def _upstream_failure(exc: demo_buyer.DemoBuyerError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


@router.post("/scenario")
async def create_scenario(
    body: ScenarioRequest,
    _membership: Membership = Depends(require_company_role("owner", "admin")),
):
    try:
        return await demo_buyer.build_scenario(body.model_dump())
    except demo_buyer.DemoBuyerError as exc:
        raise _upstream_failure(exc) from exc


@router.post("/reply")
async def create_reply(
    body: ReplyRequest,
    _membership: Membership = Depends(require_company_role("owner", "admin")),
):
    try:
        return await demo_buyer.buyer_reply(
            body.persona.model_dump(),
            body.language,
            body.voice,
            [t.model_dump() for t in body.history],
            body.seller_text,
        )
    except demo_buyer.DemoBuyerError as exc:
        raise _upstream_failure(exc) from exc
