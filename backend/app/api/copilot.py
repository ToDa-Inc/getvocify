"""Live call objection copilot API."""

from __future__ import annotations

import json
from typing import Literal, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from supabase import Client

from app.deps import get_supabase, get_user_id
from app.services.copilot.suggest import stream_objection_suggestion

router = APIRouter(prefix="/api/v1/copilot", tags=["copilot"])


class SuggestRequest(BaseModel):
    transcript_window: str = Field(..., max_length=20000)
    latest_turn: str = Field(..., max_length=4000)
    product_context: Optional[str] = Field(default=None, max_length=8000)
    language: Literal["auto", "en", "es"] = "auto"
    call_mode: Literal["speakerphone", "softphone", "meeting"] = "speakerphone"
    speaker_role: Literal["prospect", "rep", "unknown"] = "unknown"


@router.post("/suggest")
async def suggest_objection_handling(
    body: SuggestRequest,
    user_id: str = Depends(get_user_id),
    supabase: Client = Depends(get_supabase),
):
    """Stream a structured objection-handling suggestion (SSE)."""
    product_context = (body.product_context or "").strip()
    if not product_context:
        # Desktop meetings don't carry the offer; use the one the rep saved for extraction.
        from app.services.extraction_context import load_product_context

        product_context = load_product_context(supabase, user_id)

    async def event_gen():
        async for event in stream_objection_suggestion(
            transcript_window=body.transcript_window,
            latest_turn=body.latest_turn,
            product_context=product_context or None,
            language=body.language,
            call_mode=body.call_mode,
            speaker_role=body.speaker_role,
        ):
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
