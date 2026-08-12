"""Live call objection copilot API."""

from __future__ import annotations

import json
from typing import Literal, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.deps import get_user_id
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
    _user_id: str = Depends(get_user_id),
):
    """Stream a structured objection-handling suggestion (SSE)."""

    async def event_gen():
        async for event in stream_objection_suggestion(
            transcript_window=body.transcript_window,
            latest_turn=body.latest_turn,
            product_context=body.product_context,
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
