"""
HubSpot OAuth flow: authorize URL and token exchange.
"""

import jwt
from datetime import datetime, timedelta
from typing import Optional
import httpx

from app.config import settings

HUBSPOT_AUTHORIZE_URL = "https://app.hubspot.com/oauth/authorize"
HUBSPOT_TOKEN_URL = "https://api.hubapi.com/oauth/v1/token"

# Scopes from app-hsmeta.json (must match HubSpot app config)
HUBSPOT_OAUTH_SCOPES = [
    "oauth",
    "crm.objects.contacts.read",
    "crm.objects.contacts.write",
    "crm.objects.companies.read",
    "crm.objects.companies.write",
    "crm.objects.deals.read",
    "crm.objects.deals.write",
    "crm.schemas.contacts.read",
    "crm.schemas.companies.read",
    "crm.schemas.deals.read",
]


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
