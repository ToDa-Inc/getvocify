"""Read contact CRM properties for the cold-call brief. Reuses Ask's CRM layer."""

from __future__ import annotations

import asyncio
import logging

from app.services.briefs.cold_call import translate_crm_source

logger = logging.getLogger(__name__)

HUBSPOT_PROFILE_PROPERTIES = [
    "jobtitle",
    "company",
    "createdate",
    "hs_analytics_source",
    "hs_lead_source",
]

_PROFILE_READER = None


class ContactProfileReadFailed(Exception):
    """CRM contact properties could not be read."""


def set_contact_profile_reader(reader) -> None:
    """reader(connection, contact_id) -> profile dict. None uses the live CRM."""
    global _PROFILE_READER
    _PROFILE_READER = reader


def read_contact_profile(connection: dict, contact_id: str) -> dict | None:
    """Best-effort contact profile for the brief. None when the CRM cannot answer."""
    if _PROFILE_READER is not None:
        return _PROFILE_READER(connection, contact_id)
    provider = str(connection.get("provider") or "").strip().lower()
    if provider not in {"hubspot", "pipedrive"}:
        return None
    try:
        return asyncio.run(_live_profile(connection, contact_id, provider))
    except ContactProfileReadFailed:
        raise
    except Exception as exc:
        logger.warning("brief contact profile read failed", exc_info=True)
        raise ContactProfileReadFailed from exc


async def _live_profile(connection: dict, contact_id: str, provider: str) -> dict | None:
    if provider == "hubspot":
        return await _hubspot_profile(connection, contact_id)
    return await _pipedrive_profile(connection, contact_id)


async def _hubspot_profile(connection: dict, contact_id: str) -> dict | None:
    from app.services.crm_copilot.tools import HubSpotBundle
    from app.services.crm_providers import build_crm_provider

    provider = build_crm_provider(None, connection)
    hs = HubSpotBundle.from_provider(provider)
    try:
        obj = await hs.contacts.get(contact_id, properties=HUBSPOT_PROFILE_PROPERTIES)
    except Exception as exc:
        raise ContactProfileReadFailed from exc
    props = getattr(obj, "properties", None) or (obj.get("properties") if isinstance(obj, dict) else {}) or {}
    company = " ".join(str(props.get("company") or "").split()) or None
    source = translate_crm_source(
        provider="hubspot",
        analytics_source=props.get("hs_analytics_source"),
        lead_source=props.get("hs_lead_source"),
    )
    created = props.get("createdate")
    profile = {
        "jobtitle": " ".join(str(props.get("jobtitle") or "").split()) or None,
        "company_name": company,
        "source_label": source,
        "created_at": created,
        "source_ref": contact_id,
    }
    motion = " ".join(str(props.get("sales_motion_key") or "").split()) or None
    if motion:
        profile["sales_motion_key"] = motion
    return {key: value for key, value in profile.items() if value is not None}


async def _pipedrive_profile(connection: dict, contact_id: str) -> dict | None:
    from app.services.crm_copilot.pipedrive_reads import PipedriveReader
    from app.services.crm_providers import build_crm_provider

    provider = build_crm_provider(None, connection)
    reader = PipedriveReader.from_provider(provider)
    try:
        brief = await reader.hydrate_contact(contact_id, ctx=None)
    except Exception as exc:
        raise ContactProfileReadFailed from exc
    org = brief.get("company") if isinstance(brief.get("company"), dict) else {}
    fields = brief.get("fields") if isinstance(brief.get("fields"), dict) else {}
    source = translate_crm_source(provider="pipedrive", analytics_source=None, lead_source=fields.get("label"))
    profile = {
        "jobtitle": brief.get("jobtitle"),
        "company_name": org.get("name") or brief.get("company_name"),
        "source_label": source,
        "created_at": fields.get("add_time"),
        "source_ref": contact_id,
    }
    return {key: value for key, value in profile.items() if value is not None}
