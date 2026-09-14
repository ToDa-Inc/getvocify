"""The endpoint HubSpot calls to obtain a playable recording URL.

Unauthenticated by design — HubSpot calls it server-to-server. The Twilio
CallSid in the path is the secret. If HubSpot also sends `externalAccountId`,
it must match `hubspot_hub_id` on the call. The URL returned is a short-lived
Supabase signed URL, which honours `Range` and returns `206` so HubSpot's
player can seek.
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
        .eq("carrier_call_id", external_id)
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
    # HubSpot's recordings/ready probe often omits query params and only
    # substitutes %s with hs_call_external_id (the Twilio CallSid). CallSid is
    # the secret. Fail only when HubSpot claims a different portal.
    if account_id and hub_id and hub_id != account_id:
        logger.warning(
            "Recording %s denied: hub_id=%r externalAccountId=%r appId=%r",
            external_id, hub_id, account_id, (appId or "").strip(),
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Wrong account"
        )

    url = StorageService(supabase).signed_call_recording_url(
        row["recording_path"], settings.CALL_RECORDING_URL_TTL_SECONDS
    )
    return {"authenticatedUrl": url}
