"""Authenticated calling endpoints for the Chrome extension.

The browser never holds Twilio credentials. It asks for a short-lived
AccessToken whose identity is the Vocify user id; the voice webhook later
trusts that identity (Twilio signs it) to resolve the caller ID.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from supabase import Client
from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import VoiceGrant

from app.config import settings
from app.deps import get_supabase, get_user_id
from app.services.telephony.caller_id import (
    list_caller_ids,
    start_caller_id_verification,
)
from app.services.telephony.twilio_client import telephony_configured
from app.services.telephony.twiml import InvalidPhoneNumber

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/calls", tags=["calls"])

TOKEN_TTL_SECONDS = 3600


class CallerIdRequest(BaseModel):
    phoneNumber: str = Field(min_length=6, max_length=32)
    label: Optional[str] = Field(default=None, max_length=64)


def mint_voice_access_token(user_id: str, ttl: int = TOKEN_TTL_SECONDS) -> str:
    """Twilio AccessToken with a VoiceGrant scoped to our TwiML App."""
    if not (
        settings.TWILIO_ACCOUNT_SID
        and settings.TWILIO_API_KEY_SID
        and settings.TWILIO_API_KEY_SECRET
        and settings.TWILIO_TWIML_APP_SID
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Calling is not configured on this environment",
        )

    token = AccessToken(
        settings.TWILIO_ACCOUNT_SID,
        settings.TWILIO_API_KEY_SID,
        settings.TWILIO_API_KEY_SECRET,
        identity=str(user_id),
        ttl=ttl,
    )
    # incoming_allow stays False: inbound callbacks go to the SDR's own phone.
    token.add_grant(
        VoiceGrant(outgoing_application_sid=settings.TWILIO_TWIML_APP_SID)
    )
    return token.to_jwt()


@router.get("/config")
async def get_calling_config(
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """Whether calling is available here, plus this user's caller IDs."""
    if not telephony_configured():
        return {"enabled": False, "callerIds": []}
    return {"enabled": True, "callerIds": list_caller_ids(supabase, user_id)}


@router.post("/token")
async def create_voice_token(user_id: str = Depends(get_user_id)):
    return {
        "token": mint_voice_access_token(user_id),
        "identity": str(user_id),
        "expiresIn": TOKEN_TTL_SECONDS,
    }


@router.get("/caller-ids")
async def get_caller_ids(
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    return {"callerIds": list_caller_ids(supabase, user_id)}


@router.post("/caller-ids")
async def create_caller_id(
    body: CallerIdRequest,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """Start Twilio verification. Twilio calls the number in English, so the
    caller must be shown `verificationCode` to type on the keypad."""
    if not telephony_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Calling is not configured on this environment",
        )
    try:
        result = start_caller_id_verification(
            supabase, user_id, body.phoneNumber, body.label
        )
    except InvalidPhoneNumber as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e
    return {**result, "verificationCode": result.get("verificationCode")}
