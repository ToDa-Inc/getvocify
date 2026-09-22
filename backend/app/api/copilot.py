"""Live call objection copilot API."""

from __future__ import annotations

import json
from typing import Literal, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from supabase import Client

from app.deps import get_membership, get_supabase
from app.services.company import Membership
from app.services.copilot.context import resolve_suggest_context
from app.services.copilot.load_grounding import load_company_suggest_grounding, load_suggest_grounding
from app.services.copilot.suggest import stream_objection_suggestion

router = APIRouter(prefix="/api/v1/copilot", tags=["copilot"])


class SuggestRequest(BaseModel):
    transcript_window: str = Field(..., max_length=20000)
    latest_turn: str = Field(..., max_length=4000)
    product_context: Optional[str] = Field(default=None, max_length=8000)
    language: Literal["auto", "en", "es"] = "auto"
    call_mode: Literal["speakerphone", "softphone", "meeting"] = "speakerphone"
    speaker_role: Literal["prospect", "rep", "unknown"] = "unknown"
    capture_id: Optional[str] = Field(default=None, max_length=128)
    contact_id: Optional[str] = Field(default=None, max_length=128)
    request_id: Optional[str] = Field(default=None, max_length=128)


@router.post("/suggest")
async def suggest_objection_handling(
    body: SuggestRequest,
    membership: Membership = Depends(get_membership),
    supabase: Client = Depends(get_supabase),
):
    """Stream a structured objection-handling suggestion (SSE)."""

    context = resolve_suggest_context(
        body.contact_id,
        call_mode=body.call_mode,
    )
    if body.capture_id:
        grounding = load_suggest_grounding(
            supabase,
            user_id=membership.user_id,
            company_id=membership.company_id,
            capture_id=body.capture_id,
            context=context,
        )
    else:
        grounding = load_company_suggest_grounding(
            supabase,
            company_id=membership.company_id,
            call_mode=body.call_mode,
            context=context,
        )

    async def event_gen():
        async for event in stream_objection_suggestion(
            transcript_window=body.transcript_window,
            latest_turn=body.latest_turn,
            product_context=body.product_context,
            language=body.language,
            call_mode=body.call_mode,
            speaker_role=body.speaker_role,
            grounding=grounding,
            context=context,
        ):
            if event.get("type") == "result":
                if body.capture_id:
                    event = {**event, "capture_id": body.capture_id}
                if body.request_id:
                    event = {**event, "request_id": body.request_id}
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        yield "data: {\"type\": \"done\"}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/health")
async def copilot_health():
    return {"ok": True, "feature": "objection-copilot"}
