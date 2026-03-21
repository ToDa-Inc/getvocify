"""Salesforce OAuth 2.0 Web Server flow."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlencode

import httpx
import jwt

from app.config import settings


def salesforce_oauth_enabled() -> bool:
    return bool(
        settings.SALESFORCE_CLIENT_ID
        and settings.SALESFORCE_CLIENT_SECRET
        and settings.SALESFORCE_REDIRECT_URI
        and settings.JWT_SECRET
    )


def build_authorize_url(user_id: str) -> str:
    if not salesforce_oauth_enabled():
        raise RuntimeError(
            "Salesforce OAuth not configured. Set SALESFORCE_CLIENT_ID, "
            "SALESFORCE_CLIENT_SECRET, SALESFORCE_REDIRECT_URI, JWT_SECRET."
        )
    state = jwt.encode(
        {"user_id": user_id, "exp": datetime.utcnow() + timedelta(minutes=10)},
        settings.JWT_SECRET,
        algorithm="HS256",
    )
    scopes = "api refresh_token"
    params = {
        "response_type": "code",
        "client_id": settings.SALESFORCE_CLIENT_ID,
        "redirect_uri": settings.SALESFORCE_REDIRECT_URI,
        "scope": scopes,
        "state": state,
    }
    base = settings.SALESFORCE_LOGIN_BASE.rstrip("/")
    return f"{base}/services/oauth2/authorize?{urlencode(params)}"


def decode_state(state: str) -> Optional[str]:
    if not settings.JWT_SECRET:
        return None
    try:
        payload = jwt.decode(state, settings.JWT_SECRET, algorithms=["HS256"])
        return payload.get("user_id")
    except jwt.PyJWTError:
        return None


async def exchange_code_for_tokens(code: str) -> dict:
    token_url = f"{settings.SALESFORCE_LOGIN_BASE.rstrip('/')}/services/oauth2/token"
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": settings.SALESFORCE_CLIENT_ID,
        "client_secret": settings.SALESFORCE_CLIENT_SECRET,
        "redirect_uri": settings.SALESFORCE_REDIRECT_URI,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(token_url, data=data, timeout=30.0)
        resp.raise_for_status()
        return resp.json()
