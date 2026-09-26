"""Read contact CRM properties for the cold-call brief. Reuses Ask's CRM layer."""

from __future__ import annotations

import asyncio
import logging

from app.services.briefs.cold_call import hubspot_source_label

logger = logging.getLogger(__name__)

HUBSPOT_PROFILE_PROPERTIES = ["jobtitle", "company", "createdate", "hs_analytics_source"]


class ContactProfileReadFailed(Exception):
    """CRM contact properties could not be read."""


def read_contact_profile(supabase, connection: dict, contact_id: str) -> dict | None:
    """Contact profile for the brief. None when the CRM has no profile read (Salesforce and others)."""
    provider = str(connection.get("provider") or "").strip().lower()
    if provider not in {"hubspot", "pipedrive"}:
        return None
    try:
        if provider == "hubspot":
            return asyncio.run(_hubspot_profile(supabase, connection, contact_id))
        return asyncio.run(_pipedrive_profile(supabase, connection, contact_id))
    except Exception as exc:
        logger.warning("brief contact profile read failed", exc_info=True)
        raise ContactProfileReadFailed from exc


def _clean(value) -> str | None:
    return " ".join(str(value or "").split()) or None


async def _hubspot_profile(supabase, connection: dict, contact_id: str) -> dict:
    from app.services.crm_copilot.tools import HubSpotBundle
    from app.services.crm_providers import build_crm_provider

    hs = HubSpotBundle.from_provider(build_crm_provider(supabase, connection))
    obj = await hs.contacts.get(contact_id, properties=HUBSPOT_PROFILE_PROPERTIES)
    props = getattr(obj, "properties", None) or (obj.get("properties") if isinstance(obj, dict) else {}) or {}
    profile = {
        "jobtitle": _clean(props.get("jobtitle")),
        "company_name": _clean(props.get("company")),
        "source_label": hubspot_source_label(props.get("hs_analytics_source")),
        "created_at": props.get("createdate"),
        "source_ref": contact_id,
    }
    return {key: value for key, value in profile.items() if value is not None}


async def _pipedrive_profile(supabase, connection: dict, contact_id: str) -> dict:
    """Pipedrive has no documented lead-origin field on a person, so there is no origin part."""
    from app.services.crm_copilot.pipedrive_reads import PipedriveReader
    from app.services.crm_providers import build_crm_provider

    reader = PipedriveReader.from_provider(build_crm_provider(supabase, connection))
    brief = await reader.hydrate_contact(contact_id, ctx=None)
    org = brief.get("company") if isinstance(brief.get("company"), dict) else {}
    fields = brief.get("fields") if isinstance(brief.get("fields"), dict) else {}
    profile = {
        "jobtitle": _clean(brief.get("jobtitle")),
        "company_name": _clean(org.get("name") or brief.get("company_name")),
        "created_at": fields.get("add_time"),
        "source_ref": contact_id,
    }
    return {key: value for key, value in profile.items() if value is not None}
