"""
HubSpot OAuth flow: authorize URL, token exchange, and access-token refresh.
"""

import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx
import jwt

from app.config import settings

logger = logging.getLogger(__name__)

HUBSPOT_AUTHORIZE_URL = "https://app.hubspot.com/oauth/authorize"
HUBSPOT_TOKEN_URL = "https://api.hubapi.com/oauth/v1/token"

# HubSpot OAuth access tokens expire in ~30 minutes; refresh before that.
TOKEN_REFRESH_BUFFER = timedelta(minutes=5)

# Scopes from app-hsmeta.json (must match HubSpot app config)
HUBSPOT_OAUTH_SCOPES = [
    "oauth",
    "crm.objects.contacts.read",
    "crm.objects.contacts.write",
    "crm.objects.companies.read",
    "crm.objects.companies.write",
    "crm.objects.deals.read",
    "crm.objects.deals.write",
    "crm.objects.owners.read",
    "crm.objects.line_items.read",
    "crm.objects.line_items.write",
    "crm.schemas.contacts.read",
    "crm.schemas.companies.read",
    "crm.schemas.deals.read",
    "crm.schemas.line_items.read",
    # Added for call-outcome self-provisioning (see
    # app/services/hubspot/call_outcome.py:ensure_call_outcome_capability) -
    # the ONLY thing this scope is used for is adding the VOCIFY_LOST /
    # VOCIFY_FOLLOW_UP options to hs_lead_status and creating the
    # vocify_lost_reason property on first use. Portals that authorized
    # before this scope existed do NOT have it retroactively - they must
    # reconnect HubSpot before the Call outcome buttons can appear (see
    # ensure_call_outcome_capability's fail-closed behavior). Do not widen
    # its usage beyond that one provisioning call.
    "crm.schemas.contacts.write",
]

_refresh_locks: dict[str, threading.Lock] = {}
_refresh_locks_guard = threading.Lock()


def _lock_for(connection_id: str) -> threading.Lock:
    with _refresh_locks_guard:
        if connection_id not in _refresh_locks:
            _refresh_locks[connection_id] = threading.Lock()
        return _refresh_locks[connection_id]


def oauth_enabled() -> bool:
    """Check if OAuth credentials are configured."""
    return bool(
        settings.HUBSPOT_CLIENT_ID
        and settings.HUBSPOT_CLIENT_SECRET
        and settings.HUBSPOT_REDIRECT_URI
        and settings.JWT_SECRET
    )


def build_authorize_url(user_id: str) -> str:
    """
    Build HubSpot OAuth authorize URL with signed state.
    
    State is a JWT encoding user_id and exp to prevent CSRF.
    """
    if not oauth_enabled():
        raise RuntimeError(
            "HubSpot OAuth not configured. Set HUBSPOT_CLIENT_ID, "
            "HUBSPOT_CLIENT_SECRET, HUBSPOT_REDIRECT_URI, and JWT_SECRET."
        )

    state_payload = {
        "user_id": user_id,
        "exp": datetime.utcnow() + timedelta(minutes=10),
    }
    state = jwt.encode(
        state_payload,
        settings.JWT_SECRET,
        algorithm="HS256",
    )

    params = {
        "client_id": settings.HUBSPOT_CLIENT_ID,
        "redirect_uri": settings.HUBSPOT_REDIRECT_URI,
        "scope": " ".join(HUBSPOT_OAUTH_SCOPES),
        "state": state,
    }
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{HUBSPOT_AUTHORIZE_URL}?{qs}"


def decode_state(state: str) -> Optional[str]:
    """
    Decode and validate state JWT, return user_id or None if invalid.
    """
    if not settings.JWT_SECRET:
        return None
    try:
        payload = jwt.decode(
            state,
            settings.JWT_SECRET,
            algorithms=["HS256"],
        )
        return payload.get("user_id")
    except jwt.PyJWTError:
        return None


async def exchange_code_for_tokens(code: str) -> dict:
    """
    Exchange authorization code for access and refresh tokens.
    
    Returns:
        dict with access_token, refresh_token, expires_in (seconds)
    
    Raises:
        RuntimeError if OAuth not configured
        httpx.HTTPStatusError if HubSpot returns an error
    """
    if not oauth_enabled():
        raise RuntimeError("HubSpot OAuth not configured.")

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.HUBSPOT_REDIRECT_URI,
        "client_id": settings.HUBSPOT_CLIENT_ID,
        "client_secret": settings.HUBSPOT_CLIENT_SECRET,
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            HUBSPOT_TOKEN_URL,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15.0,
        )
        response.raise_for_status()
        return response.json()


async def refresh_access_token(refresh_token: str) -> dict:
    """
    Exchange a HubSpot OAuth refresh token for new access + refresh tokens.

    Returns:
        dict with access_token, refresh_token (optional rotation), expires_in

    Raises:
        RuntimeError if OAuth client is not configured
        httpx.HTTPStatusError if HubSpot rejects the refresh (e.g. refresh token expired)
    """
    if not oauth_enabled():
        raise RuntimeError("HubSpot OAuth not configured.")

    if not refresh_token or not refresh_token.strip():
        raise ValueError("Missing refresh token")

    data = {
        "grant_type": "refresh_token",
        "client_id": settings.HUBSPOT_CLIENT_ID,
        "client_secret": settings.HUBSPOT_CLIENT_SECRET,
        "refresh_token": refresh_token.strip(),
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            HUBSPOT_TOKEN_URL,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15.0,
        )
        response.raise_for_status()
        return response.json()


def _parse_expires_at(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError):
        return None


def _token_needs_refresh(connection: dict[str, Any]) -> bool:
    """True if access token is missing expiry, expired, or within refresh buffer."""
    expires_at = _parse_expires_at(connection.get("token_expires_at"))
    if expires_at is None:
        # Unknown expiry — refresh if we have a refresh_token (OAuth), skip private apps.
        return bool(connection.get("refresh_token"))
    return datetime.now(timezone.utc) >= (expires_at - TOKEN_REFRESH_BUFFER)


def refresh_hubspot_tokens(refresh_token: str) -> dict:
    """
    Sync exchange of refresh_token for a new access_token (and possibly rotated refresh_token).

    Returns HubSpot token payload. Raises httpx.HTTPStatusError on failure.
    """
    if not settings.HUBSPOT_CLIENT_ID or not settings.HUBSPOT_CLIENT_SECRET:
        raise RuntimeError("HubSpot OAuth client credentials are not configured.")
    if not refresh_token:
        raise ValueError("refresh_token is required")

    with httpx.Client(timeout=15.0) as client:
        response = client.post(
            HUBSPOT_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": settings.HUBSPOT_CLIENT_ID,
                "client_secret": settings.HUBSPOT_CLIENT_SECRET,
                "refresh_token": refresh_token,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        return response.json()


def ensure_fresh_hubspot_connection(supabase: Any, connection: dict[str, Any]) -> dict[str, Any]:
    """
    Ensure crm_connections row has a non-expired HubSpot access_token.

    HubSpot OAuth access tokens expire in ~30 minutes. Refresh tokens last longer
    and must be used to obtain new access tokens. Persists updates to Supabase.

    Returns the connection dict (possibly updated in-memory).
    """
    if not connection:
        return connection
    if connection.get("status") and connection.get("status") != "connected":
        return connection
    if not _token_needs_refresh(connection):
        return connection

    refresh_token = (connection.get("refresh_token") or "").strip()
    if not refresh_token:
        # Private app / PAT — no refresh path
        return connection

    connection_id = str(connection.get("id") or "")
    lock = _lock_for(connection_id) if connection_id else threading.Lock()

    with lock:
        # Re-read after acquiring lock to avoid duplicate refreshes
        if connection_id and supabase is not None:
            try:
                fresh = (
                    supabase.table("crm_connections")
                    .select("id, access_token, refresh_token, token_expires_at, status")
                    .eq("id", connection_id)
                    .single()
                    .execute()
                )
                if fresh.data:
                    connection = {**connection, **fresh.data}
                    if not _token_needs_refresh(connection):
                        return connection
                    refresh_token = (connection.get("refresh_token") or "").strip() or refresh_token
            except Exception as e:
                logger.warning("HubSpot token re-read failed: %s", e)

        try:
            data = refresh_hubspot_tokens(refresh_token)
        except Exception as e:
            logger.warning(
                "HubSpot token refresh failed for connection %s: %s",
                connection_id or "unknown",
                e,
            )
            raise

        access_token = data.get("access_token")
        if not access_token:
            raise RuntimeError("HubSpot refresh response missing access_token")

        expires_in = int(data.get("expires_in") or 1800)
        new_expires = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()
        new_refresh = data.get("refresh_token") or refresh_token
        now = datetime.now(timezone.utc).isoformat()

        update = {
            "access_token": access_token,
            "refresh_token": new_refresh,
            "token_expires_at": new_expires,
            "updated_at": now,
        }
        if connection_id and supabase is not None:
            try:
                supabase.table("crm_connections").update(update).eq("id", connection_id).execute()
            except Exception as e:
                logger.warning("HubSpot token persist failed for %s: %s", connection_id, e)

        connection = {**connection, **update}
        logger.info("HubSpot access token refreshed for connection %s", connection_id or "unknown")
        return connection
