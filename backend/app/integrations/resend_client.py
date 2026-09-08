"""Resend client for transactional emails (invites, password reset)."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

DEFAULT_FROM_EMAIL = "hello@getvocify.com"

_resend_client: Optional["ResendClient"] = None


def get_resend_from_email(display_name: Optional[str] = None) -> str:
    raw = (settings.RESEND_FROM_EMAIL or DEFAULT_FROM_EMAIL).strip()
    address = raw
    if "<" in raw and ">" in raw:
        address = raw.split("<", 1)[1].rsplit(">", 1)[0].strip() or DEFAULT_FROM_EMAIL
    name = (display_name or "").strip()
    if name:
        return f"{name} <{address}>"
    return raw or DEFAULT_FROM_EMAIL


class ResendClientError(Exception):
    pass


class ResendClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.RESEND_API_KEY
        if not self.api_key:
            raise ValueError("RESEND_API_KEY is not configured")
        self.base_url = "https://api.resend.com"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def send_email(
        self,
        to: str,
        subject: str,
        html: str,
        from_email: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not from_email:
            from_email = get_resend_from_email()
        payload = {
            "from": from_email,
            "to": [to],
            "subject": subject,
            "html": html,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/emails",
                headers=self.headers,
                json=payload,
            )
        if response.status_code >= 400:
            raise ResendClientError(
                f"Resend API error {response.status_code}: {response.text[:500]}"
            )
        return response.json()


def get_resend_client() -> Optional[ResendClient]:
    global _resend_client
    if not settings.RESEND_API_KEY:
        return None
    if _resend_client is None:
        _resend_client = ResendClient()
    return _resend_client
