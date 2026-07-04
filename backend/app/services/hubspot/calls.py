"""
HubSpot call engagement helpers: fetch properties, associations, download recording.
"""

from __future__ import annotations

from typing import Any, Optional

import httpx

from .client import HubSpotClient
from .exceptions import HubSpotError, HubSpotNotFoundError


CALL_PROPERTIES = (
    "hs_call_recording_url",
    "hs_call_status",
    "hs_call_duration",
    "hs_call_title",
    "hs_call_from_number",
    "hs_call_to_number",
    "hs_timestamp",
)


async def get_call_engagement(client: HubSpotClient, call_id: str) -> Optional[dict[str, Any]]:
    """GET /crm/v3/objects/calls/{id} with call properties."""
    props = ",".join(CALL_PROPERTIES)
    try:
        data = await client.get(f"/crm/v3/objects/calls/{call_id}", params={"properties": props})
    except HubSpotNotFoundError:
        return None
    except HubSpotError as e:
        if getattr(e, "status_code", None) == 404:
            return None
        raise
    if not data:
        return None
    return data


async def list_association_ids(client: HubSpotClient, call_id: str, to_object_type: str) -> list[str]:
    """List associated object IDs for a call (deals or contacts)."""
    endpoint = f"/crm/v3/objects/calls/{call_id}/associations/{to_object_type}"
    try:
        data = await client.get(endpoint)
    except HubSpotError:
        return []
    if not data:
        return []
    results = data.get("results") or []
    out: list[str] = []
    for r in results:
        oid = r.get("id")
        if oid is not None:
            out.append(str(oid))
    return out


async def get_call_associations(client: HubSpotClient, call_id: str) -> tuple[list[str], list[str]]:
    """Returns (deal_ids, contact_ids)."""
    deals = await list_association_ids(client, call_id, "deals")
    contacts = await list_association_ids(client, call_id, "contacts")
    return deals, contacts


async def download_recording(recording_url: str, access_token: str) -> tuple[bytes, str]:
    """
    Download call recording bytes. Try Bearer (HubSpot-hosted) first, then plain GET.
    """
    if not recording_url or not recording_url.startswith("http"):
        raise ValueError("Invalid recording URL")

    headers_bearer = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as http:
        r = await http.get(recording_url, headers=headers_bearer)
        if r.status_code in (401, 403):
            r2 = await http.get(recording_url)
            r2.raise_for_status()
            ct = r2.headers.get("content-type", "audio/mpeg").split(";")[0].strip()
            return r2.content, ct
        r.raise_for_status()
        ct = r.headers.get("content-type", "audio/mpeg").split(";")[0].strip()
        return r.content, ct
