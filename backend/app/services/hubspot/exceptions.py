"""
Custom exceptions for HubSpot API errors.

Provides granular error handling with specific exception types
for different failure scenarios.
"""

from __future__ import annotations
from typing import Optional


class HubSpotError(Exception):
    """Base exception for all HubSpot-related errors"""
    
    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_data: Optional[dict] = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.response_data = response_data or {}


class HubSpotAuthError(HubSpotError):
    """
    Raised when authentication fails (401).
    
    Common causes:
    - Invalid or expired access token
    - Token format is incorrect
    """
    pass


class HubSpotScopeError(HubSpotError):
    """
    Raised when the token lacks required permissions (403).
    
    Common causes:
    - Missing required scopes in Private App configuration
    - Token doesn't have write access when needed
    """
    
    def __init__(
        self,
        message: str,
        required_scope: Optional[str] = None,
        status_code: Optional[int] = None,
        response_data: Optional[dict] = None,
    ):
        super().__init__(message, status_code, response_data)
        self.required_scope = required_scope


class HubSpotNotFoundError(HubSpotError):
    """
    Raised when a requested resource doesn't exist (404).
    
    Common causes:
    - Object ID doesn't exist
    - Invalid object type ID
    """
    pass


class HubSpotConflictError(HubSpotError):
    """
    Raised when a conflict occurs (409).
    
    Common causes:
    - Duplicate unique identifier (e.g., email already exists)
    - Concurrent modification conflict
    """
    pass


class HubSpotRateLimitError(HubSpotError):
    """
    Raised when rate limit is exceeded (429).
    
    HubSpot limits:
    - 100 requests per 10 seconds (most endpoints)
    - 4 requests per second (search endpoints)
    """
    
    def __init__(
        self,
        message: str,
        retry_after: Optional[int] = None,
        status_code: Optional[int] = None,
        response_data: Optional[dict] = None,
    ):
        super().__init__(message, status_code, response_data)
        self.retry_after = retry_after


class HubSpotServerError(HubSpotError):
    """
    Raised when HubSpot API returns a server error (5xx).
    
    These are transient errors that may succeed on retry.
    """
    pass


class HubSpotValidationError(HubSpotError):
    """
    Raised when request validation fails (400).
    
    Common causes:
    - Invalid property values
    - Missing required properties
    - Invalid date format
    """
    pass

