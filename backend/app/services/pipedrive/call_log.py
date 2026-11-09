"""Log Vocify-placed calls in Pipedrive as done call activities (the Pipedrive side of hubspot/call_log.py).

A call nobody answered carries no memo note (see followup_logic.SKIPPED_SCREENING), so this activity is its only
trace in the CRM. An answered call's summary and transcript reach Pipedrive as the memo's note once the rep approves;
the activity only says the call happened, how long it lasted and who made it.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from supabase import Client

from app.services.company_scope import get_crm_connection
from app.services.crm_providers.calling import dialable_phone
from app.services.hubspot.call_log import hubspot_call_body_for_disposition

from .client import PipedriveClient, unwrap_data
from .search import PipedriveSearchService

logger = logging.getLogger(__name__)


def pipedrive_only_connection(supabase: Client, user_id: str) -> Optional[dict]:
    """The company's connected Pipedrive, when it has no HubSpot to log the call in instead."""
    try:
        if get_crm_connection(supabase, user_id, "hubspot"):
            return None
        connection = get_crm_connection(supabase, user_id, "pipedrive")
    except Exception:
        logger.warning("Could not read the CRM connections of %s", user_id, exc_info=True)
        return None
    return connection if connection and connection.get("status") == "connected" else None


def _phones(person: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for phone in person.get("phones") or person.get("phone") or []:
        value = phone.get("value") if isinstance(phone, dict) else phone
        if value:
            out.append(str(value))
    return out


async def person_id_for_number(search: PipedriveSearchService, number: str) -> Optional[str]:
    """The one person whose number is the dialed one; none when no person or several have it."""
    wanted = dialable_phone(number)
    if not wanted:
        return None
    hits = await search.search_persons(wanted, fields="phone", limit=5)
    ids = {
        str(hit["id"])
        for hit in hits
        if hit.get("id") is not None and any(dialable_phone(phone) == wanted for phone in _phones(hit))
    }
    return ids.pop() if len(ids) == 1 else None


def _duration(seconds: float) -> str:
    """HH:MM, the only form v2 activities take (HH:MM:SS and seconds are refused); a connected call under a minute is 00:01."""
    total = max(int(round((seconds or 0) / 60)), 1 if seconds and seconds > 0 else 0)
    return f"{total // 60:02d}:{total % 60:02d}"


def _occurred_at(row: dict, duration: float) -> datetime:
    """When the call ended: from its own times, so a late retry does not move it to another day."""
    for field, extra in (("answered_at", duration), ("created_at", 0.0)):
        try:
            at = datetime.fromisoformat(str(row[field]).replace("Z", "+00:00")) + timedelta(seconds=extra)
        except (KeyError, TypeError, ValueError):
            continue
        return (at if at.tzinfo else at.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
    return datetime.now(timezone.utc)


async def _call_type(client: PipedriveClient) -> Optional[str]:
    rows = unwrap_data(await client.get("/activityTypes", version="v1"))
    by_icon: Optional[str] = None
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or row.get("is_deleted"):
            continue
        if row.get("key_string") == "call":
            return "call"
        if row.get("icon_key") == "call" and not by_icon:
            by_icon = row.get("key_string")
    return by_icon


async def log_call(supabase: Client, connection: dict, row: dict, *, duration: float, disposition: str) -> Optional[str]:
    """Create the call's activity. Best-effort: a Pipedrive failure never fails the call or its memo."""
    from app.api.crm_pipedrive import _pd_client_from_row
    from .sync import _get_pipedrive_owner_id_for_user

    call_sid = row.get("carrier_call_id")
    try:
        client = _pd_client_from_row(connection, supabase)
        search = PipedriveSearchService(client)
        person_id = row.get("hubspot_contact_id") or await person_id_for_number(search, row.get("to_number") or "")
        if not person_id:
            logger.info("Pipedrive call logging skipped for %s: no person matches the dialed number", call_sid)
            return None
        call_type = await _call_type(client)
        if not call_type:
            logger.warning("Pipedrive call logging skipped for %s: no 'call' activity type", call_sid)
            return None
        person = await search.get_person(str(person_id))
        name = (person.get("name") or "").strip()
        occurred = _occurred_at(row, duration)
        body: dict[str, Any] = {
            "subject": f"Llamada con {name}" if name else (row.get("to_number") or "Llamada Vocify"),
            "type": call_type,
            "done": True,
            "due_date": occurred.date().isoformat(),
            "due_time": occurred.strftime("%H:%M"),
            "note": hubspot_call_body_for_disposition(disposition),
            # v2 activities: person_id is read-only, the person goes in as the primary participant.
            "participants": [{"person_id": int(person_id), "primary": True}],
        }
        if row.get("hubspot_deal_id"):
            body["deal_id"] = int(row["hubspot_deal_id"])
        owner_id = await _get_pipedrive_owner_id_for_user(client, supabase, row["user_id"], connection["id"])
        if owner_id:
            body["owner_id"] = int(owner_id)
        if duration and disposition in ("connected", "unprocessed"):
            body["duration"] = _duration(duration)
        try:
            created = unwrap_data(await client.post("/activities", json_body=body))
        except Exception:
            if "duration" not in body:
                raise
            # A duration Pipedrive refuses must not lose the call: log it without.
            body.pop("duration")
            created = unwrap_data(await client.post("/activities", json_body=body))
        activity_id = str(created["id"]) if isinstance(created, dict) and created.get("id") is not None else None
        if not activity_id:
            return None
        state = dict(row.get("provider_state") or {})
        supabase.table("outbound_calls").update(
            {"status": "logged", "provider_state": {**state, "pipedrive_activity_id": activity_id}}
        ).eq("carrier_call_id", call_sid).execute()
        return activity_id
    except Exception:
        logger.warning("Pipedrive call logging failed for %s", call_sid, exc_info=True)
        return None


def already_logged(row: dict) -> bool:
    return bool((row.get("provider_state") or {}).get("pipedrive_activity_id"))
