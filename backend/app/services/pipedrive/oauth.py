"""Pipedrive Marketplace OAuth 2.0 (oauth.pipedrive.com)."""

from __future__ import annotations

import base64
import logging
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlencode

import httpx
import jwt

from app.config import settings

logger = logging.getLogger(__name__)

AUTHORIZE_URL = "https://oauth.pipedrive.com/oauth/authorize"
TOKEN_URL = "https://oauth.pipedrive.com/oauth/token"


def pipedrive_oauth_enabled() -> bool:
    return bool(
        settings.PIPEDRIVE_CLIENT_ID
        and settings.PIPEDRIVE_CLIENT_SECRET
        and settings.PIPEDRIVE_REDIRECT_URI
        and settings.JWT_SECRET
    )


def _basic_auth_header() -> str:
    raw = f"{settings.PIPEDRIVE_CLIENT_ID}:{settings.PIPEDRIVE_CLIENT_SECRET}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


def build_authorize_url(user_id: str) -> str:
    if not pipedrive_oauth_enabled():
        raise RuntimeError(
            "Pipedrive OAuth not configured. Set PIPEDRIVE_CLIENT_ID, "
            "PIPEDRIVE_CLIENT_SECRET, PIPEDRIVE_REDIRECT_URI, JWT_SECRET."
        )
    state = jwt.encode(
        {"user_id": user_id, "exp": datetime.utcnow() + timedelta(minutes=10)},
        settings.JWT_SECRET,
        algorithm="HS256",
    )
    params = {
        "client_id": settings.PIPEDRIVE_CLIENT_ID,
        "redirect_uri": settings.PIPEDRIVE_REDIRECT_URI,
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def decode_state(state: str) -> Optional[str]:
    if not settings.JWT_SECRET:
        return None
    try:
        payload = jwt.decode(state, settings.JWT_SECRET, algorithms=["HS256"])
        return payload.get("user_id")
    except jwt.PyJWTError:
        return None


async def exchange_code_for_tokens(code: str) -> dict:
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.PIPEDRIVE_REDIRECT_URI,
    }
    headers = {
        "Authorization": _basic_auth_header(),
        "Content-Type": "application/x-www-form-urlencoded",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(TOKEN_URL, data=data, headers=headers, timeout=30.0)
        if resp.is_error:
            logger.error(
                "Pipedrive token exchange failed: status=%s body=%s",
                resp.status_code,
                (resp.text or "")[:2000],
            )
        resp.raise_for_status()
        return resp.json()


async def refresh_tokens(refresh_token: str) -> dict:
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    headers = {
        "Authorization": _basic_auth_header(),
        "Content-Type": "application/x-www-form-urlencoded",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(TOKEN_URL, data=data, headers=headers, timeout=30.0)
        if resp.status_code != 200:
            from .exceptions import PipedriveAuthError

            raise PipedriveAuthError(
                f"Token refresh failed: {resp.text}",
                status_code=resp.status_code,
            )
        return resp.json()
