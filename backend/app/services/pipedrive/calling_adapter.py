"""Pipedrive: the person to call for the person, deal or organization on screen.

Reads the same cached record context the extension uses (`app/api/crm_pipedrive.py`).
A deal or organization is callable only through its one person.
"""

from __future__ import annotations

import logging

from supabase import Client

from app.services.crm_providers.calling import NO_CONTEXT, Callee, RecordContext, dialable_phone
from app.services.live_calls.crm_url import CrmRecord

logger = logging.getLogger(__name__)


class PipedriveCallingAdapter:
    provider = "pipedrive"

    async def record_context(self, record: CrmRecord, *, supabase: Client, user_id: str) -> RecordContext:
        from app.api import crm_pipedrive as pipedrive_api

        loaders = {
            "contact": pipedrive_api.get_pipedrive_person_context,
            "deal": pipedrive_api.get_pipedrive_deal_context,
            "company": pipedrive_api.get_pipedrive_org_context,
            "lead": pipedrive_api.get_pipedrive_lead_context,
            "activity": pipedrive_api.get_pipedrive_activity_context,
        }
        try:
            context = await loaders[record.object_type](record.record_id, supabase=supabase, user_id=user_id) or {}
        except Exception:
            logger.warning("Pipedrive record context failed for %s %s", record.object_type, record.record_id, exc_info=True)
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
        if record.object_type in ("contact", "lead") or (record.object_type == "activity" and not context.get("contacts")):
            return RecordContext(callee=callee, contacts_count=1 if callee else 0)
        return RecordContext(callee=callee, contacts_count=len(context.get("contacts") or []))
