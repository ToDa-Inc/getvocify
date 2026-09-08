"""Authenticated calling endpoints for the Chrome extension.

The browser never holds Twilio credentials. It asks for a short-lived
AccessToken whose identity is the Vocify user id; the voice webhook later
trusts that identity (Twilio signs it) to resolve the caller ID.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from supabase import Client
from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import VoiceGrant

from app.config import settings
from app.deps import get_supabase, get_user_id
from app.services.telephony.caller_id import (
    confirm_caller_id_verification,
    delete_caller_id,
    get_caller_id,
    list_caller_ids,
    set_default_caller_id,
    start_caller_id_verification,
    update_caller_id_label,
    CallerIdNotVerified,
    CallerIdVerificationUnsupported,
)
from app.services.telephony.provider import calling_provider
from app.services.telephony.telnyx_client import TelnyxNotConfigured
from app.services.telephony.telnyx_credentials import (
    ensure_user_credential,
    mint_telnyx_voice_token,
)
from app.services.telephony.twilio_client import telephony_configured
from app.services.telephony.twiml import InvalidPhoneNumber

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/calls", tags=["calls"])

TOKEN_TTL_SECONDS = 3600


class CallerIdRequest(BaseModel):
    phoneNumber: str = Field(min_length=6, max_length=32)
    label: Optional[str] = Field(default=None, max_length=64)


class CallerIdPatchRequest(BaseModel):
    isDefault: Optional[bool] = None
    label: Optional[str] = Field(default=None, max_length=64)


class CallerIdConfirmRequest(BaseModel):
    phoneNumber: str
    code: str = Field(min_length=4, max_length=12)


def _settings_url() -> str:
    return f"{(settings.FRONTEND_URL or '').rstrip('/')}/dashboard/settings#caller-id"


def _http_from_telnyx_status(exc: httpx.HTTPStatusError) -> HTTPException:
    code = exc.response.status_code if exc.response is not None else 400
    if 400 <= code < 500:
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Telnyx rejected this caller ID verification",
        )
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="Telnyx caller ID verification failed",
    )


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
        region=settings.TWILIO_REGION or None,
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
    hubspot_logging = bool(settings.HUBSPOT_APP_ID)
    provider = calling_provider()
    if not telephony_configured():
        return {
            "enabled": False,
            "provider": provider,
            "callerIds": [],
            "hubspotLogging": hubspot_logging,
            "settingsUrl": _settings_url(),
        }
    if provider == "telnyx":
        try:
            ensure_user_credential(supabase, user_id)
        except TelnyxNotConfigured as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Calling is not configured on this environment",
            ) from e
    return {
        "enabled": True,
        "provider": provider,
        "callerIds": list_caller_ids(supabase, user_id),
        "hubspotLogging": hubspot_logging,
        "settingsUrl": _settings_url(),
    }


@router.post("/token")
async def create_voice_token(
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    if calling_provider() == "telnyx":
        try:
            return mint_telnyx_voice_token(supabase, user_id)
        except TelnyxNotConfigured as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Calling is not configured on this environment",
            ) from e
    return {
        "token": mint_voice_access_token(user_id),
        "identity": str(user_id),
        "expiresIn": TOKEN_TTL_SECONDS,
        "provider": calling_provider(),
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
    """Start caller-ID verification.

    Twilio calls the number in English and returns `verificationCode` to type
    on the keypad. Telnyx sends an OTP to the handset; the client must POST
    `/caller-ids/confirm` (`needsCodeSubmit: true`). Never invent a Telnyx code.
    """
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
    except CallerIdVerificationUnsupported as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        ) from e
    except httpx.HTTPStatusError as e:
        raise _http_from_telnyx_status(e) from e
    if result.get("needsCodeSubmit"):
        return result
    return {**result, "verificationCode": result.get("verificationCode")}


@router.post("/caller-ids/confirm")
async def confirm_caller_id(
    body: CallerIdConfirmRequest,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """Telnyx only. Twilio confirm is the keypad on the verification call."""
    if calling_provider() != "telnyx":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Caller ID confirm is only supported for Telnyx",
        )
    try:
        return confirm_caller_id_verification(
            supabase, user_id, body.phoneNumber, body.code
        )
    except InvalidPhoneNumber as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e
    except CallerIdNotVerified as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
        ) from e
    except httpx.HTTPStatusError as e:
        raise _http_from_telnyx_status(e) from e


@router.patch("/caller-ids/{phone_number}")
async def patch_caller_id(
    phone_number: str,
    body: CallerIdPatchRequest,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """Set default or rename. Does not call Twilio."""
    try:
        existing = get_caller_id(supabase, user_id, phone_number)
    except InvalidPhoneNumber as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Caller ID not found"
        )
    if body.label is not None:
        update_caller_id_label(supabase, user_id, phone_number, body.label)
    if body.isDefault is True:
        if not set_default_caller_id(supabase, user_id, phone_number):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only a verified number can be the default",
            )
    return {"callerIds": list_caller_ids(supabase, user_id)}


@router.delete("/caller-ids/{phone_number}")
async def remove_caller_id(
    phone_number: str,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    try:
        deleted = delete_caller_id(supabase, user_id, phone_number)
    except InvalidPhoneNumber as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Caller ID not found"
        )
    return {"ok": True}


def _call_summary(row: dict, memo_status: Optional[str] = None) -> dict:
    return {
        "callSid": row.get("carrier_call_id"),
        "to": row.get("to_number"),
        "from": row.get("from_number"),
        "contactId": row.get("hubspot_contact_id"),
        "dealId": row.get("hubspot_deal_id"),
        "engagementId": row.get("hubspot_engagement_id"),
        "status": row.get("status"),
        "startedAt": row.get("created_at"),
        "answeredAt": row.get("answered_at"),
        "durationSeconds": row.get("recording_duration"),
        "memoId": row.get("memo_id"),
        "memoStatus": memo_status,
        "errorMessage": row.get("error_message"),
    }


def _memo_status_by_id(supabase: Client, memo_ids: list) -> dict:
    ids = [mid for mid in memo_ids if mid]
    if not ids:
        return {}
    rows = (
        supabase.table("memos")
        .select("id,status")
        .in_("id", ids)
        .execute()
        .data
    ) or []
    return {row.get("id"): row.get("status") for row in rows}


@router.get("/history")
async def list_call_history(
    limit: int = Query(20, ge=1, le=100),
    contactId: Optional[str] = None,
    dealId: Optional[str] = None,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    query = (
        supabase.table("outbound_calls")
        .select(
            "carrier_call_id,to_number,from_number,hubspot_contact_id,"
            "hubspot_deal_id,hubspot_engagement_id,status,created_at,"
            "answered_at,recording_duration,memo_id,error_message"
        )
        .eq("user_id", user_id)
    )
    if contactId:
        query = query.eq("hubspot_contact_id", contactId)
    if dealId:
        query = query.eq("hubspot_deal_id", dealId)
    rows = (query.order("created_at", desc=True).limit(limit).execute().data) or []
    statuses = _memo_status_by_id(supabase, [r.get("memo_id") for r in rows])
    return {
        "calls": [
            _call_summary(row, statuses.get(row.get("memo_id"))) for row in rows
        ]
    }


@router.get("/{call_sid}")
async def get_call(
    call_sid: str,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    rows = (
        supabase.table("outbound_calls")
        .select(
            "carrier_call_id,to_number,from_number,hubspot_contact_id,"
            "hubspot_deal_id,hubspot_engagement_id,status,created_at,"
            "answered_at,recording_duration,memo_id,error_message"
        )
        .eq("user_id", user_id)
        .eq("carrier_call_id", call_sid)
        .limit(1)
        .execute()
        .data
    ) or []
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Call not found"
        )
    row = rows[0]
    statuses = _memo_status_by_id(supabase, [row.get("memo_id")])
    return _call_summary(row, statuses.get(row.get("memo_id")))
