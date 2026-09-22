"""Capture adapter: reserve a memo and finalize input review."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from supabase import Client

from app.deps import get_membership, get_supabase
from app.services.captures import (
    CaptureContentConflict,
    CaptureIdentity,
    complete_capture,
    reserve_capture,
    store_capture_audio,
)
from app.services.company import Membership

router = APIRouter(prefix="/api/v1/captures", tags=["captures"])


class CreateCaptureRequest(BaseModel):
    client_capture_id: str = Field(min_length=1, max_length=128)
    started_at: datetime
    interaction_kind: str
    sales_motion_key: Optional[str] = None
    playbook_version_id: Optional[str] = None
    company_id: Optional[str] = None


class CaptureResponse(BaseModel):
    capture_id: str
    memo_id: str
    status: str
    audio_status: str = "partial"


class CompleteCaptureRequest(BaseModel):
    transcript: Optional[str] = None
    audio_duration: Optional[float] = None
    turns: Optional[list[Any]] = None
    transcript_complete: bool = True
    audio_status: Optional[str] = None


def _to_response(identity: CaptureIdentity) -> CaptureResponse:
    return CaptureResponse(
        capture_id=identity.capture_id,
        memo_id=identity.memo_id,
        status=identity.status,
        audio_status=identity.audio_status,
    )


@router.post("", response_model=CaptureResponse)
async def create_capture(
    body: CreateCaptureRequest,
    supabase: Client = Depends(get_supabase),
    membership: Membership = Depends(get_membership),
):
    identity = reserve_capture(
        supabase,
        user_id=membership.user_id,
        company_id=membership.company_id,
        client_capture_id=body.client_capture_id,
        started_at=body.started_at,
        interaction_kind=body.interaction_kind,
        sales_motion_key=body.sales_motion_key,
        playbook_version_id=body.playbook_version_id,
    )
    return _to_response(identity)


@router.post("/{capture_id}/complete", response_model=CaptureResponse)
async def complete_capture_endpoint(
    capture_id: str,
    body: CompleteCaptureRequest,
    supabase: Client = Depends(get_supabase),
    membership: Membership = Depends(get_membership),
):
    try:
        identity = complete_capture(
            supabase,
            user_id=membership.user_id,
            company_id=membership.company_id,
            capture_id=capture_id,
            transcript=body.transcript,
            audio_duration=body.audio_duration,
            turns=body.turns,
            transcript_complete=body.transcript_complete,
            audio_status=body.audio_status,
        )
    except CaptureContentConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "capture_id": exc.capture_id,
                "memo_id": exc.memo_id,
                "status": exc.status,
                "needs_new_review": exc.needs_new_review,
            },
        ) from exc

    if identity.should_start_pipeline and not identity.needs_batch_stt and (body.transcript or "").strip():
        from app.api.memos import start_extraction_from_transcript

        await start_extraction_from_transcript(
            identity.memo_id,
            membership.user_id,
            (body.transcript or "").strip(),
            supabase,
            source_type="meeting_transcript",
        )
    return _to_response(identity)


@router.put("/{capture_id}/audio", response_model=CaptureResponse)
async def upload_capture_audio(
    capture_id: str,
    request: Request,
    supabase: Client = Depends(get_supabase),
    membership: Membership = Depends(get_membership),
):
    audio = await request.body()
    content_type = request.headers.get("content-type", "application/octet-stream")
    declared = request.headers.get("content-length")
    byte_length = int(declared) if declared and declared.isdigit() else len(audio)
    identity = store_capture_audio(
        supabase,
        user_id=membership.user_id,
        capture_id=capture_id,
        audio=audio,
        content_type=content_type,
        byte_length=byte_length,
    )
    return _to_response(identity)
