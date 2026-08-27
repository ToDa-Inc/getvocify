"""The endpoint HubSpot calls to obtain a playable recording URL.

Unauthenticated by design — HubSpot calls it server-to-server. Authorization is
the pairing of an unguessable Twilio CallSid with the `externalAccountId` of the
hub that owns the call. The URL returned is a short-lived Supabase signed URL,
which honours `Range` and returns `206` so HubSpot's player can seek.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from supabase import Client

from app.config import settings
from app.deps import get_supabase
from app.services.storage import StorageService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/public/hubspot", tags=["hubspot-recordings"])


@router.get("/recordings/{external_id}")
async def get_authenticated_recording(
    external_id: str,
    externalAccountId: str = Query(default=""),
    appId: str = Query(default=""),
    supabase: Client = Depends(get_supabase),
):
    found = (
        supabase.table("outbound_calls")
        .select("recording_path,hubspot_hub_id")
        .eq("twilio_call_sid", external_id)
        .limit(1)
        .execute()
    )
    row = (found.data or [None])[0]
    if not row or not row.get("recording_path"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Recording not found"
        )

    hub_id = (row.get("hubspot_hub_id") or "").strip()
    account_id = (externalAccountId or "").strip()
    if not hub_id or not account_id or hub_id != account_id:
        logger.warning(
            "Recording %s denied: hub_id=%r externalAccountId=%r",
            external_id, hub_id, account_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Wrong account"
        )

    url = StorageService(supabase).signed_call_recording_url(
        row["recording_path"], settings.CALL_RECORDING_URL_TTL_SECONDS
    )
    return {"authenticatedUrl": url}
