"""What a CRM must answer for Vocify to call the record on screen.

Each CRM that can be called from the desktop island implements
`CRMCallingAdapter` and is registered in `calling_registry.py`. HubSpot is the
only one today; a new CRM adds its URL shapes to `live_calls/crm_url.py`, an
adapter here, and its fixture URLs to `tests/crm_providers/test_calling_contract.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol

from supabase import Client

from app.services.live_calls.crm_url import CrmRecord
from app.services.telephony.twiml import InvalidPhoneNumber, normalize_e164


@dataclass(frozen=True)
class Callee:
    """The one person a record on screen can be called at."""

    contact_id: str
    name: Optional[str]
    # E.164, or None when the CRM has no number we can dial.
    phone: Optional[str]


@dataclass(frozen=True)
class RecordContext:
    callee: Optional[Callee]
    # People on the record: 1 for a contact page, the associated contacts for a deal or company.
    contacts_count: int


NO_CONTEXT = RecordContext(callee=None, contacts_count=0)


class CRMCallingAdapter(Protocol):
    provider: str

    async def record_context(self, record: CrmRecord, *, supabase: Client, user_id: str) -> RecordContext: ...


def dialable_phone(raw: Optional[str]) -> Optional[str]:
    """The CRM's free-text phone as E.164, or None when it is not a number."""
    if not raw:
        return None
    try:
        return normalize_e164(raw)
    except InvalidPhoneNumber:
        return None
