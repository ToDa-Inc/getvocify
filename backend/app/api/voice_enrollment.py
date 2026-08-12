"""Voice enrollment API for Call Copilot (Speechmatics speaker identification)."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from supabase import Client

from app.deps import get_supabase, get_user_id
from app.services.voice_enrollment import (
    CONSENT_VERSION,
    REP_LABEL,
    VoiceEnrollmentService,
)

router = APIRouter(prefix="/api/v1/voice-enrollment", tags=["voice-enrollment"])


class EnrollmentStatusResponse(BaseModel):
    enrolled: bool
    rep_label: str = REP_LABEL
    sample_count: int = 0
    consented_at: str | None = None
    consent_version: str | None = None
    script: str


class SaveEnrollmentRequest(BaseModel):
    speaker_identifiers: List[str] = Field(..., min_length=1, max_length=50)
    consent: bool = False
    sample_count: int = Field(default=1, ge=1, le=5)
    rep_label: str = REP_LABEL


ENROLLMENT_SCRIPT = (
    "Hola, esta es mi configuración de voz para Call Copilot. "
    "Vendo Vocify: notas de voz que actualizan HubSpot después de las llamadas de ventas. "
    "Cuando un prospecto dice que es demasiado caro, pregunto si es el precio en sí "
    "o el momento del desembolso. Cuando dicen llámame más tarde, pregunto qué tendría "
    "que ser verdad en treinta días. Esta grabación solo sirve para que Vocify "
    "distinga mi voz de la del prospecto con el altavoz."
)


@router.get("/status", response_model=EnrollmentStatusResponse)
async def enrollment_status(
    user_id: str = Depends(get_user_id),
    supabase: Client = Depends(get_supabase),
):
    status_data = VoiceEnrollmentService(supabase).get_status(user_id)
    return EnrollmentStatusResponse(**status_data, script=ENROLLMENT_SCRIPT)


@router.post("/save", response_model=EnrollmentStatusResponse)
async def save_enrollment(
    body: SaveEnrollmentRequest,
    user_id: str = Depends(get_user_id),
    supabase: Client = Depends(get_supabase),
):
    try:
        status_data = VoiceEnrollmentService(supabase).upsert_enrollment(
            user_id,
            body.speaker_identifiers,
            consent=body.consent,
            sample_count=body.sample_count,
            rep_label=body.rep_label,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return EnrollmentStatusResponse(**status_data, script=ENROLLMENT_SCRIPT)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_enrollment(
    user_id: str = Depends(get_user_id),
    supabase: Client = Depends(get_supabase),
):
    VoiceEnrollmentService(supabase).delete_enrollment(user_id)
    return None


@router.get("/consent-version")
async def consent_version():
    return {"consent_version": CONSENT_VERSION, "rep_label": REP_LABEL}
