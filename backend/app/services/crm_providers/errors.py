"""Errors for CRM connection resolution."""


class AmbiguousPrimaryCRMError(Exception):
    """More than one CRM is connected but user_profiles.primary_crm_connection_id is not set."""

    def __init__(self, message: str = "Multiple CRMs connected. Set a primary CRM in Integrations.") -> None:
        self.message = message
        super().__init__(message)


class UnsupportedCRMProviderError(Exception):
    """No adapter registered for this provider string."""

    def __init__(self, provider: str) -> None:
        super().__init__(f"Unsupported CRM provider: {provider}")
