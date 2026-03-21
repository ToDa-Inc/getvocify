"""
Build a CRM provider adapter from a crm_connections row.
"""

from __future__ import annotations

from typing import Any, Union

from supabase import Client

from app.services.crm_providers.errors import UnsupportedCRMProviderError
from app.services.crm_providers.hubspot_provider import HubSpotCRMProvider


def build_crm_provider(supabase: Client, connection: dict[str, Any]) -> Union[HubSpotCRMProvider, Any]:
    """
    Return provider implementation for sync/preview/match.

    Raises UnsupportedCRMProviderError for unknown providers.
    """
    provider = (connection.get("provider") or "").lower()
    if provider == "hubspot":
        return HubSpotCRMProvider(supabase, connection)
    if provider == "salesforce":
        from app.services.crm_providers.salesforce_provider import SalesforceCRMProvider

        return SalesforceCRMProvider(supabase, connection)
    raise UnsupportedCRMProviderError(provider)
