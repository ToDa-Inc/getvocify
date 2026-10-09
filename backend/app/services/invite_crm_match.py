"""Whether an invited email matches a connected CRM's owner (Lista 3, item 3).

Reuses the exact owner lookup handoffs already rely on (`handoffs_crm.find_owner_id` via
`CrmOwnerWriter`, itself backed by `hoy/assigned.py`'s owners_request/connection_assigned_fetch)
instead of adding a second HubSpot/Pipedrive owners client. Never raises and never blocks the
invite: `None` means "no CRM connected" or "the lookup itself failed", `True`/`False` means the
lookup ran and did/did not find that email among the CRM's owners.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.services.crm_providers.errors import AmbiguousPrimaryCRMError
from app.services.crm_providers.resolve import resolve_sync_connection_for_company
from app.services.handoffs_crm import owner_writer_from_connection

logger = logging.getLogger(__name__)


def crm_owner_match_for_invite(supabase: Any, company_id: str, email: str) -> Optional[bool]:
    """None = no connected CRM (or the connection/lookup could not be resolved);
    True/False = the email was/was not found among that CRM's owners."""
    try:
        connection = resolve_sync_connection_for_company(supabase, company_id)
    except AmbiguousPrimaryCRMError:
        return None
    except Exception as exc:
        logger.warning("crm_owner_match: could not resolve CRM connection for %s: %s", company_id, exc)
        return None
    if not connection:
        return None
    try:
        writer = owner_writer_from_connection(connection)
        if writer is None:
            return None
        return writer.find_owner_id(email) is not None
    except Exception as exc:
        logger.warning("crm_owner_match: owner lookup failed for %s: %s", company_id, exc)
        return None
