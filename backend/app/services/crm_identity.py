"""Who a call was with, as the CRM says it.

A call linked to a CRM contact is named after that contact and its company: the CRM spells them right,
the transcript is a model's reading of what it heard.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from supabase import Client

logger = logging.getLogger(__name__)

# The memo is not ready until this returns, so a slow CRM must not hold it.
TIMEOUT_S = 4.0

# extraction key -> key in the CRM contact context
FIELDS = {"contactName": "contactName", "companyName": "companyName", "contactEmail": "contactEmail"}


async def crm_identity(supabase: Client, user_id: str, contact_id: Optional[str]) -> dict[str, str]:
    """The contact's name, company and email from HubSpot, only those it has; {} with no contact or no answer."""
    if not contact_id:
        return {}
    try:
        from app.api.crm import get_contact_context_for_extension

        context = await asyncio.wait_for(
            get_contact_context_for_extension(str(contact_id), supabase, user_id), TIMEOUT_S
        )
    except Exception as exc:
        logger.warning("CRM identity for contact %s unavailable: %s", contact_id, exc)
        return {}
    return {
        key: value.strip()
        for key, source in FIELDS.items()
        if isinstance(value := (context or {}).get(source), str) and value.strip()
    }


def with_crm_identity(extraction: dict[str, Any], identity: dict[str, str]) -> dict[str, Any]:
    """The extraction with the CRM's name, company and email over what was read from the transcript."""
    return {**extraction, **identity}
