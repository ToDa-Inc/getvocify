"""Log Vocify-placed calls to HubSpot and hand over the recording.

`hs_call_source = INTEGRATIONS_PLATFORM` plus the three external identifiers
are what switch HubSpot from "store a URL" to "ask the app for an authenticated
URL". That inversion is the point: Vocify holds the audio and HubSpot fetches
it, so no third-party telephony API sits between us and our own recordings.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.services.hubspot.client import HubSpotClient

logger = logging.getLogger(__name__)

# The calling-extensions recordings pipeline is documented against this version.
CALLS_OBJECT_PATH = "/crm/v3/objects/calls"
CALLING_EXTENSIONS_BASE = "/crm/extensions/calling/2026-03"

# HubSpot hs_call_status values (see Calls API docs).
HUBSPOT_STATUS_BY_DISPOSITION: dict[str, str] = {
    "connected": "COMPLETED",
    "voicemail": "COMPLETED",
    "no_response": "COMPLETED",
    "busy": "BUSY",
    "no_answer": "NO_ANSWER",
    "failed": "FAILED",
    "canceled": "CANCELED",
}

HUBSPOT_BODY_BY_DISPOSITION: dict[str, str] = {
    "connected": "Transcripcion y extraccion disponibles en Vocify.",
    "voicemail": "Buzon de voz. Transcripcion disponible en Vocify.",
    "no_response": "Sin respuesta / posible IVR. Transcripcion disponible en Vocify.",
    "busy": "Ocupado.",
    "no_answer": "Sin respuesta.",
    "failed": "Llamada fallida.",
    "canceled": "Llamada cancelada.",
}


def normalize_twilio_dial_status(dial_status: str) -> str:
    """Map Twilio DialCallStatus to outbound_calls.call_disposition."""
    raw = (dial_status or "").strip().lower()
    mapping = {
        "completed": "connected",
        "busy": "busy",
        "no-answer": "no_answer",
        "failed": "failed",
        "canceled": "canceled",
    }
    return mapping.get(raw, "failed")


def hubspot_call_status_for_disposition(disposition: str) -> str:
    return HUBSPOT_STATUS_BY_DISPOSITION.get(disposition, "COMPLETED")


def hubspot_call_body_for_disposition(disposition: str) -> str:
    return HUBSPOT_BODY_BY_DISPOSITION.get(
        disposition,
        HUBSPOT_BODY_BY_DISPOSITION["connected"],
    )


def build_call_properties(
    *,
    occurred_at: str,
    to_number: str,
    from_number: str,
    duration_ms: int,
    external_id: str,
    external_account_id: str,
    app_id: str,
    owner_id: Optional[str],
    title: str,
    body: str,
    call_status: str = "COMPLETED",
) -> dict[str, Any]:
    if not external_id:
        raise ValueError("external_id is required for the recordings pipeline")
    if not external_account_id:
        raise ValueError("external_account_id is required")
    if not app_id:
        raise ValueError("app_id is required")

    props: dict[str, Any] = {
        "hs_timestamp": occurred_at,
        "hs_call_title": title,
        "hs_call_body": body,
        "hs_call_duration": str(int(duration_ms)),
        "hs_call_from_number": from_number,
        "hs_call_to_number": to_number,
        "hs_call_status": call_status,
        "hs_call_direction": "OUTBOUND",
        "hs_call_source": "INTEGRATIONS_PLATFORM",
        "hs_call_app_id": app_id,
        "hs_call_external_id": external_id,
        "hs_call_external_account_id": external_account_id,
    }
    if owner_id:
        props["hubspot_owner_id"] = str(owner_id)
    return props


async def log_call_to_hubspot(
    client: HubSpotClient,
    *,
    properties: dict[str, Any],
    contact_id: Optional[str],
    deal_id: Optional[str],
) -> str:
    """Create the engagement and associate it, returning the engagement id."""
    created = await client.post(CALLS_OBJECT_PATH, data={"properties": properties})
    engagement_id = str((created or {}).get("id") or "")
    if not engagement_id:
        raise RuntimeError("HubSpot did not return a call engagement id")

    for object_type, object_id in (("contacts", contact_id), ("deals", deal_id)):
        if not object_id:
            continue
        try:
            await client.put(
                f"{CALLS_OBJECT_PATH}/{engagement_id}/associations/"
                f"{object_type}/{object_id}"
            )
        except Exception as e:
            logger.warning(
                "Could not associate call %s with %s %s: %s",
                engagement_id, object_type, object_id, e,
            )
    return engagement_id


async def mark_recording_ready(client: HubSpotClient, engagement_id: str) -> None:
    """Tell HubSpot the audio can be fetched and transcribed."""
    await client.post(
        f"{CALLING_EXTENSIONS_BASE}/recordings/ready",
        data={"engagementId": int(engagement_id)},
    )
