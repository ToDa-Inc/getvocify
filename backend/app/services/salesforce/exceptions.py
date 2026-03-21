"""Salesforce REST API errors."""

from __future__ import annotations

from typing import Any, Optional


class SalesforceError(Exception):
    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_data: Optional[dict[str, Any]] = None,
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.response_data = response_data or {}
        super().__init__(message)


class SalesforceAuthError(SalesforceError):
    pass


class SalesforceNotFoundError(SalesforceError):
    pass


class SalesforceValidationError(SalesforceError):
    pass
