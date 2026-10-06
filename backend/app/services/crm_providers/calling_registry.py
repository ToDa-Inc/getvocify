"""The CRMs Vocify can call from the desktop island (see `calling.py`)."""

from __future__ import annotations

from typing import Optional

from app.services.crm_providers.calling import CRMCallingAdapter
from app.services.hubspot.calling_adapter import HubSpotCallingAdapter

CALLING_ADAPTERS: dict[str, CRMCallingAdapter] = {
    "hubspot": HubSpotCallingAdapter(),
}


def calling_adapter(provider: Optional[str]) -> Optional[CRMCallingAdapter]:
    return CALLING_ADAPTERS.get(provider or "")
