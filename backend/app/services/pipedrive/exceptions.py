"""Pipedrive REST API errors."""

from __future__ import annotations

from typing import Any, Optional


class PipedriveError(Exception):
    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_data: Optional[dict[str, Any]] = None,
        error_code: Optional[str] = None,
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.response_data = response_data or {}
        self.error_code = error_code
        super().__init__(message)


class PipedriveAuthError(PipedriveError):
    def __init__(self, message: str, status_code: Optional[int] = None, response_data: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message, status_code=status_code, response_data=response_data, error_code="PIPEDRIVE_AUTH_EXPIRED")


class PipedriveNotFoundError(PipedriveError):
    pass


class PipedriveValidationError(PipedriveError):
    pass


class PipedriveRateLimitError(PipedriveError):
    def __init__(self, message: str, status_code: Optional[int] = None, response_data: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message, status_code=status_code, response_data=response_data, error_code="PIPEDRIVE_RATE_LIMITED")
