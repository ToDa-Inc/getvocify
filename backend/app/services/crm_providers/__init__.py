"""Multi-CRM provider layer (protocols, factory, primary connection resolution)."""

from app.services.crm_providers.errors import AmbiguousPrimaryCRMError, UnsupportedCRMProviderError
from app.services.crm_providers.factory import build_crm_provider
from app.services.crm_providers.resolve import count_connected_crms, resolve_sync_connection

__all__ = [
    "AmbiguousPrimaryCRMError",
    "UnsupportedCRMProviderError",
    "build_crm_provider",
    "resolve_sync_connection",
    "count_connected_crms",
]
