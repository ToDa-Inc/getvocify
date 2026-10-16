"""Demo buyer for sales demos (owner/admin of a company with DEMO_BUYER_ENABLED): a scenario per prospect and free replies."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.deps import get_supabase, require_company_role
from app.services import demo_buyer
from app.services.company import Membership
from app.services.feature_flags import is_enabled

router = APIRouter(prefix="/api/v1/demo", tags=["demo"])

Language = Literal["es", "en"]
DEMO_FLAG = "DEMO_BUYER_ENABLED"


def require_demo_buyer(
    membership: Membership = Depends(require_company_role("owner", "admin")),
    supabase=Depends(get_supabase),
) -> Membership:
    # Off means the route does not exist for this company: same body as an unknown path.
    if not is_enabled(supabase, membership.company_id, DEMO_FLAG):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    return membership


class ScenarioRequest(BaseModel):
    offer: str = Field(..., min_length=3, max_length=600)
    niche: str = Field(..., min_length=2, max_length=200)
    company: str | None = Field(default=None, max_length=120)
    prospect_name: str | None = Field(default=None, max_length=80)
    context: str | None = Field(default=None, max_length=600)
    language: Language = "es"
    voice: str | None = Field(default=None, max_length=40)


class Turn(BaseModel):
    role: Literal["buyer", "seller"]
    text: str = Field(..., max_length=1200)


class Persona(BaseModel):
    name: str = Field(..., max_length=120)
    gender: Literal["male", "female"] = "female"
    role: str = Field(..., max_length=160)
    company: str = Field(..., max_length=160)
    background: str = Field(..., max_length=600)


class ReplyRequest(BaseModel):
    persona: Persona
    language: Language = "es"
    voice: str = Field(default=demo_buyer.VOICES["female"], max_length=40)
    history: list[Turn] = Field(default_factory=list, max_length=40)
    seller_text: str = Field(..., min_length=1, max_length=1200)


class AnalyzeUrlRequest(BaseModel):
    url: str = Field(..., min_length=4, max_length=500)


def _upstream_failure(exc: demo_buyer.DemoBuyerError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


@router.post("/scenario")
async def create_scenario(
    body: ScenarioRequest,
    _membership: Membership = Depends(require_demo_buyer),
):
    try:
        return await demo_buyer.build_scenario(body.model_dump())
    except demo_buyer.DemoBuyerError as exc:
        raise _upstream_failure(exc) from exc


@router.post("/reply")
async def create_reply(
    body: ReplyRequest,
    _membership: Membership = Depends(require_demo_buyer),
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


@router.post("/analyze-url")
async def analyze_url(
    body: AnalyzeUrlRequest,
    _membership: Membership = Depends(require_demo_buyer),
):
    try:
        return await demo_buyer.analyze_url(body.url)
    except demo_buyer.DemoBuyerError as exc:
        raise _upstream_failure(exc) from exc
