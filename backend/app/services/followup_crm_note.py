"""Log a Vocify-sent follow-up as a CRM note (D9), reusing the existing HubSpot/Pipedrive
note-creation helpers - not sync_memo, since this only leaves a note. Best-effort: a failed
note never blocks the send (the email already went out); the caller stores this result and
shows it, it never raises.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

NOTE_HEADER = "Follow-up enviado desde Vocify"


async def log_followup_note(supabase: Any, memo: dict, body: str) -> dict:
    from app.services.crm_providers.errors import AmbiguousPrimaryCRMError
    from app.services.crm_providers.resolve import resolve_sync_connection_for_company

    company_id = memo.get("company_id")
    if not company_id:
        return {"status": "skipped", "reason": "no_company"}

    try:
        connection = resolve_sync_connection_for_company(supabase, str(company_id))
    except AmbiguousPrimaryCRMError:
        return {"status": "skipped", "reason": "ambiguous_crm"}
    except Exception as exc:
        logger.warning("followup CRM note: could not resolve connection for %s: %s", company_id, exc)
        return {"status": "skipped", "reason": "no_connection"}
    if not connection:
        return {"status": "skipped", "reason": "no_crm"}

    deal_id = memo.get("hubspot_deal_id") or None
    contact_id = memo.get("hubspot_contact_id") or None
    if not deal_id and not contact_id:
        return {"status": "skipped", "reason": "no_target"}

    provider = (connection.get("provider") or "").lower()
    try:
        if provider == "hubspot":
            note_id = await _hubspot_note(supabase, connection, deal_id, contact_id, body, memo)
        elif provider == "pipedrive":
            note_id = await _pipedrive_note(connection, deal_id, contact_id, body)
        else:
            return {"status": "skipped", "reason": "unsupported_provider"}
    except Exception as exc:
        logger.warning("followup CRM note failed (%s) for memo %s: %s", provider, memo.get("id"), exc)
        return {"status": "failed", "provider": provider, "reason": "error"}

    if not note_id:
        return {"status": "failed", "provider": provider, "reason": "no_id"}
    return {"status": "done", "provider": provider, "note_id": note_id}


async def _hubspot_note(
    supabase: Any, connection: dict, deal_id: Optional[str], contact_id: Optional[str], body: str, memo: dict,
) -> Optional[str]:
    from app.services.hubspot.associations import HubSpotAssociationService
    from app.services.hubspot.client import HubSpotClient
    from app.services.hubspot.notes import create_note_with_associations
    from app.services.hubspot.oauth import ensure_fresh_hubspot_connection

    fresh = ensure_fresh_hubspot_connection(supabase, connection)
    client = HubSpotClient(fresh["access_token"])
    associations = HubSpotAssociationService(client)
    note_properties = {
        "hs_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "hs_note_body": f"{NOTE_HEADER}\n\n{body}",
    }
    return await create_note_with_associations(
        client,
        associations,
        note_properties=note_properties,
        deal_id=deal_id,
        contact_id=contact_id,
        company_id=None,
        memo_id=str(memo.get("id") or ""),
        log_event="followup_sent_note",
    )


async def _pipedrive_note(connection: dict, deal_id: Optional[str], contact_id: Optional[str], body: str) -> Optional[str]:
    from app.services.pipedrive.client import PipedriveClient
    from app.services.pipedrive.notes import PipedriveNoteService

    meta = connection.get("metadata") or {}
    api_domain = meta.get("api_domain") or ""
    if not api_domain:
        return None
    client = PipedriveClient(
        api_domain=api_domain,
        access_token=connection["access_token"],
        refresh_token=connection.get("refresh_token"),
        connection_id=str(connection.get("id") or ""),
    )
    content = f"{NOTE_HEADER}<br><br>{body}".replace("\n", "<br>")
    return await PipedriveNoteService(client).create(content, deal_id=deal_id, person_id=contact_id)
