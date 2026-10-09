"""HubSpot: the person to call for the contact, deal or company on screen.

Reads the same cached record context the extension uses (`app/api/crm.py`).
A deal or company is callable only through its one associated contact.
"""

from __future__ import annotations

import logging

from supabase import Client

from app.services.crm_providers.calling import NO_CONTEXT, Callee, RecordContext, dialable_phone
from app.services.live_calls.crm_url import CrmRecord

logger = logging.getLogger(__name__)


class HubSpotCallingAdapter:
    provider = "hubspot"

    async def record_context(self, record: CrmRecord, *, supabase: Client, user_id: str) -> RecordContext:
        from app.api import crm as crm_api

        loaders = {
            "contact": crm_api.get_contact_context_for_extension,
            "deal": crm_api.get_deal_context_for_prefill,
            "company": crm_api.get_company_context_for_extension,
        }
        try:
            context = await loaders[record.object_type](record.record_id, supabase=supabase, user_id=user_id) or {}
        except Exception:
            logger.warning("HubSpot record context failed for %s %s", record.object_type, record.record_id, exc_info=True)
            return NO_CONTEXT
        contact_id = context.get("contactId")
        callee = (
            Callee(
                contact_id=str(contact_id),
                name=context.get("contactName") or None,
                phone=dialable_phone(context.get("contactPhone")),
            )
            if contact_id
            else None
        )
        if record.object_type == "contact":
            return RecordContext(callee=callee, contacts_count=1 if callee else 0)
        return RecordContext(callee=callee, contacts_count=len(context.get("contacts") or []))
