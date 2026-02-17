"""
Low-level HTTP client for HubSpot API.

Handles authentication, request/response processing, error handling,
rate limiting, and retries.
"""

from __future__ import annotations

import asyncio
import httpx
from typing import Any, Optional
from datetime import datetime, timedelta

from .exceptions import (
    HubSpotError,
    HubSpotAuthError,
    HubSpotScopeError,
    HubSpotNotFoundError,
    HubSpotConflictError,
    HubSpotRateLimitError,
    HubSpotServerError,
    HubSpotValidationError,
)


class HubSpotClient:
    """
    HTTP client for HubSpot CRM API.
    
    Features:
    - Automatic authentication header injection
    - Comprehensive error handling with specific exceptions
    - Automatic retry for transient failures
    - Rate limit awareness
    - Request/response logging (optional)
    """
    
    BASE_URL = "https://api.hubapi.com"
    DEFAULT_TIMEOUT = 30.0
    MAX_RETRIES = 3
    RETRY_DELAY_BASE = 1.0  # Base delay in seconds for exponential backoff
    
    # Rate limits (requests per time window)
    RATE_LIMIT_REQUESTS = 100
    RATE_LIMIT_WINDOW = 10  # seconds
    
    def __init__(self, access_token: str):
        """
        Initialize HubSpot client.
        
        Args:
            access_token: HubSpot Private App access token or OAuth token
        """
        if not access_token or not access_token.strip():
            raise ValueError("Access token cannot be empty")
        
        self.access_token = access_token.strip()
        self._rate_limit_tracker: list[datetime] = []
    
    def _get_headers(self) -> dict[str, str]:
        """Get default headers for API requests"""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
    
    def _check_rate_limit(self) -> None:
        """
        Check if we're approaching rate limit.
        
        HubSpot allows 100 requests per 10 seconds.
        This is a simple in-memory tracker. For production,
        consider using Redis or similar for distributed rate limiting.
        """
        now = datetime.utcnow()
        window_start = now - timedelta(seconds=self.RATE_LIMIT_WINDOW)
        
        # Remove old requests outside the window
        self._rate_limit_tracker = [
            ts for ts in self._rate_limit_tracker if ts > window_start
        ]
        
        # Check if we're at the limit
        if len(self._rate_limit_tracker) >= self.RATE_LIMIT_REQUESTS:
            # Calculate wait time until oldest request expires
            oldest = min(self._rate_limit_tracker)
            wait_seconds = (oldest + timedelta(seconds=self.RATE_LIMIT_WINDOW) - now).total_seconds()
            raise HubSpotRateLimitError(
                f"Rate limit exceeded. Wait {wait_seconds:.1f} seconds.",
                retry_after=int(wait_seconds) + 1,
            )
        
        # Track this request
        self._rate_limit_tracker.append(now)
    
    def _handle_error_response(
        self,
        status_code: int,
        response_data: Optional[dict[str, Any]],
    ) -> None:
        """
        Convert HTTP error response to appropriate exception.
        
        Args:
            status_code: HTTP status code
            response_data: Response body as dict
            
        Raises:
            Appropriate HubSpotError subclass
        """
        error_message = "Unknown error"
        if response_data:
            error_message = response_data.get("message", str(response_data))
        
        if status_code == 401:
            raise HubSpotAuthError(
                f"Authentication failed: {error_message}",
                status_code=status_code,
                response_data=response_data or {},
            )
        elif status_code == 403:
            # Try to extract scope information
            required_scope = None
            if response_data and "requiredScopes" in response_data:
                required_scope = ", ".join(response_data["requiredScopes"])
            
            raise HubSpotScopeError(
                f"Missing permissions: {error_message}",
                required_scope=required_scope,
                status_code=status_code,
                response_data=response_data or {},
            )
        elif status_code == 404:
            raise HubSpotNotFoundError(
                f"Resource not found: {error_message}",
                status_code=status_code,
                response_data=response_data or {},
            )
        elif status_code == 409:
            raise HubSpotConflictError(
                f"Conflict: {error_message}",
                status_code=status_code,
                response_data=response_data or {},
            )
        elif status_code == 429:
            retry_after = None
            if response_data and "retryAfter" in response_data:
                retry_after = int(response_data["retryAfter"])
            
            raise HubSpotRateLimitError(
                f"Rate limit exceeded: {error_message}",
                retry_after=retry_after,
                status_code=status_code,
                response_data=response_data or {},
            )
        elif status_code >= 500:
            raise HubSpotServerError(
                f"HubSpot server error: {error_message}",
                status_code=status_code,
                response_data=response_data or {},
            )
        elif status_code == 400:
            raise HubSpotValidationError(
                f"Validation error: {error_message}",
                status_code=status_code,
                response_data=response_data or {},
            )
        else:
            raise HubSpotError(
                f"API error ({status_code}): {error_message}",
                status_code=status_code,
                response_data=response_data or {},
            )
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
        retry_count: int = 0,
    ) -> Optional[dict[str, Any]]:
        """
        Make HTTP request to HubSpot API with retry logic.
        
        Args:
            method: HTTP method (GET, POST, PATCH, DELETE)
            endpoint: API endpoint (e.g., "/crm/v3/objects/contacts")
            data: Request body (for POST/PATCH)
            params: Query parameters
            retry_count: Current retry attempt (internal)
            
        Returns:
            Response JSON as dict, or None for 204 No Content
            
        Raises:
            HubSpotError or subclass for API errors
        """
        # Check rate limit before making request
        self._check_rate_limit()
        
        url = f"{self.BASE_URL}{endpoint}"
        headers = self._get_headers()
        
        try:
            async with httpx.AsyncClient(timeout=self.DEFAULT_TIMEOUT) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=data,
                    params=params,
                )
                
                # Handle successful responses
                if response.status_code == 204:
                    return None
                
                if 200 <= response.status_code < 300:
                    # Try to parse JSON, fallback to empty dict
                    try:
                        return response.json()
                    except Exception:
                        return {}
                
                # Handle errors
                try:
                    error_data = response.json()
                except Exception:
                    error_data = {"message": response.text or "Unknown error"}
                
                self._handle_error_response(response.status_code, error_data)
                
        except HubSpotRateLimitError as e:
            # Retry rate limit errors after waiting
            if retry_count < self.MAX_RETRIES and e.retry_after:
                await asyncio.sleep(e.retry_after)
                return await self._request(method, endpoint, data, params, retry_count + 1)
            raise
        
        except HubSpotServerError as e:
            # Retry server errors with exponential backoff
            if retry_count < self.MAX_RETRIES:
                delay = self.RETRY_DELAY_BASE * (2 ** retry_count)
                await asyncio.sleep(delay)
                return await self._request(method, endpoint, data, params, retry_count + 1)
            raise
        
        except httpx.TimeoutException:
            raise HubSpotError("Request timeout")
        
        except httpx.RequestError as e:
            raise HubSpotError(f"Request failed: {str(e)}")
    
    async def get(
        self,
        endpoint: str,
        params: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        """GET request"""
        return await self._request("GET", endpoint, params=params)
    
    async def post(
        self,
        endpoint: str,
        data: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        """POST request"""
        return await self._request("POST", endpoint, data=data)
    
    async def patch(
        self,
        endpoint: str,
        data: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """PATCH request"""
        return await self._request("PATCH", endpoint, data=data)
    
    async def put(
        self,
        endpoint: str,
        data: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        """PUT request"""
        return await self._request("PUT", endpoint, data=data)
    
    async def delete(
        self,
        endpoint: str,
    ) -> None:
        """DELETE request"""
        await self._request("DELETE", endpoint)

