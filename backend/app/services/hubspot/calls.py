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

MAX_RECORDINGS_PER_RECORD = 20
RECENT_RECORDINGS_LIMIT = 20


def call_duration_ms(props: dict) -> int:
    """Raw HubSpot hs_call_duration (milliseconds)."""
    raw = props.get("hs_call_duration")
    if raw is None or raw == "":
        return 0
    try:
        ms = float(str(raw).strip())
    except ValueError:
        return 0
    if ms < 0:
        return 0
    return int(round(ms))


def call_duration_seconds(props: dict) -> float:
    """HubSpot stores hs_call_duration in milliseconds (e.g. 3800 = 3.8s)."""
    ms = call_duration_ms(props)
    if not ms:
        return 0.0
    return round(ms / 1000.0, 2)


def parse_call_summary(data: dict[str, Any]) -> dict[str, Any]:
    props = data.get("properties") or {}
    rec = (props.get("hs_call_recording_url") or "").strip()
    ts_raw = props.get("hs_timestamp")
    ts_ms: Optional[int] = None
    if ts_raw is not None and str(ts_raw).strip():
        try:
            ts_ms = int(str(ts_raw).strip())
        except ValueError:
            ts_ms = None
    title = (props.get("hs_call_title") or "").strip() or "Call"
    return {
        "call_id": str(data.get("id")),
        "title": title,
        "timestamp_ms": ts_ms,
        "duration_ms": call_duration_ms(props),
        "duration_seconds": call_duration_seconds(props),
        "has_recording": bool(rec),
    }


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


async def list_associated_call_ids(
    client: HubSpotClient,
    from_object_type: str,
    record_id: str,
    *,
    limit: int = MAX_RECORDINGS_PER_RECORD,
) -> list[str]:
    """Call IDs associated with a deal or contact (newest association order from HubSpot)."""
    endpoint = f"/crm/v4/objects/{from_object_type}/{record_id}/associations/calls"
    try:
        data = await client.get(endpoint, params={"limit": min(limit, 500)})
    except HubSpotError:
        return []
    if not data:
        return []
    ids: list[str] = []
    for result in data.get("results") or []:
        # HubSpot v4 often returns flat { toObjectId, associationTypes }
        oid = (
            result.get("toObjectId")
            or result.get("objectId")
            or result.get("id")
        )
        if oid is not None:
            ids.append(str(oid))
            continue
        # Older/nested shapes: { to: [{ toObjectId }] }
        for to_item in result.get("to") or []:
            nested = to_item.get("toObjectId") or to_item.get("id")
            if nested is not None:
                ids.append(str(nested))
    # Preserve order, dedupe
    seen: set[str] = set()
    out: list[str] = []
    for cid in ids:
        if cid not in seen:
            seen.add(cid)
            out.append(cid)
    return out[:limit]


async def batch_get_calls(client: HubSpotClient, call_ids: list[str]) -> list[dict[str, Any]]:
    if not call_ids:
        return []
    props = list(CALL_PROPERTIES)
    results: list[dict[str, Any]] = []
    for i in range(0, len(call_ids), 100):
        chunk = call_ids[i : i + 100]
        body = {
            "inputs": [{"id": cid} for cid in chunk],
            "properties": props,
        }
        resp = await client.post("/crm/v3/objects/calls/batch/read", data=body)
        if resp and resp.get("results"):
            results.extend(resp["results"])
    return results


async def list_recordings_for_record(
    client: HubSpotClient,
    from_object_type: str,
    record_id: str,
    *,
    limit: int = MAX_RECORDINGS_PER_RECORD,
) -> list[dict[str, Any]]:
    """Summaries for calls linked to a deal, contact, or company, newest first."""
    call_ids = await list_associated_call_ids(
        client, from_object_type, record_id, limit=limit
    )
    if not call_ids:
        return []
    raw = await batch_get_calls(client, call_ids)
    items = [parse_call_summary(c) for c in raw if c.get("id")]
    items.sort(key=lambda x: x.get("timestamp_ms") or 0, reverse=True)
    return items[:limit]


async def list_recent_recordings(
    client: HubSpotClient,
    *,
    limit: int = RECENT_RECORDINGS_LIMIT,
) -> list[dict[str, Any]]:
    """Newest HubSpot calls with a recording, across the portal."""
    body = {
        "filterGroups": [{
            "filters": [{
                "propertyName": "hs_call_recording_url",
                "operator": "HAS_PROPERTY",
            }],
        }],
        "sorts": [{"propertyName": "hs_timestamp", "direction": "DESCENDING"}],
        "properties": list(CALL_PROPERTIES),
        "limit": min(max(limit, 1), 100),
    }
    try:
        data = await client.post("/crm/v3/objects/calls/search", data=body)
    except HubSpotError:
        return []
    results = (data or {}).get("results") or []
    items = [parse_call_summary(c) for c in results if c.get("id")]
    return [item for item in items if item.get("has_recording")]


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
