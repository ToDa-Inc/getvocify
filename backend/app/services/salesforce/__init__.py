"""Salesforce REST integration (Opportunity / Account / Contact)."""

from app.services.salesforce.client import SalesforceClient
from app.services.salesforce.oauth import build_authorize_url, exchange_code_for_tokens, salesforce_oauth_enabled
from app.services.salesforce.sync import SalesforceSyncService
from app.services.salesforce.validation import SalesforceValidationService

__all__ = [
    "SalesforceClient",
    "SalesforceSyncService",
    "SalesforceValidationService",
    "build_authorize_url",
    "exchange_code_for_tokens",
    "salesforce_oauth_enabled",
]
