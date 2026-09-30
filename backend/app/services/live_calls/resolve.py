"""Find the CRM contact behind a live call's phone number."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from supabase import Client

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResolvedContact:
    contact_id: str
    name: Optional[str] = None


def display_name(properties: dict) -> Optional[str]:
    first = (properties.get("firstname") or "").strip()
    last = (properties.get("lastname") or "").strip()
    full = " ".join(part for part in (first, last) if part)
    return full or (properties.get("email") or "").strip() or None


async def hubspot_contact_by_phone(
    supabase: Client,
    user_id: str,
    phone: str,
) -> Optional[ResolvedContact]:
    """Unique HubSpot contact for a number, or None. Never raises."""
    try:
        from app.api.crm import get_hubspot_client_from_connection
        from app.services.hubspot.search import HubSpotSearchService, choose_dialed_contact

        client = get_hubspot_client_from_connection(user_id, supabase)
        hits = await HubSpotSearchService(client).find_contacts_by_phone(
            phone,
            limit=5,
            default_country_code=settings.CALLING_DEFAULT_COUNTRY_CODE,
        )
        chosen = choose_dialed_contact(hits, phone)
    except Exception as e:
        logger.warning("Live call phone lookup failed: %s", e)
        return None
    if chosen is None:
        return None
    return ResolvedContact(
        contact_id=str(chosen.id),
        name=display_name(chosen.properties or {}),
    )
