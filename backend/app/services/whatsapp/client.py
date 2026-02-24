"""
WhatsApp Cloud API client.
Sends messages, interactive buttons; downloads media.
"""

import logging
from typing import Optional

import httpx

from app.config import settings
from app.services.whatsapp.webhook_parser import IncomingMessage

logger = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.facebook.com/v21.0"


class WhatsAppClient:
    """
    Meta WhatsApp Cloud API client.
    Requires WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID.
    """

    def __init__(self) -> None:
        self.access_token = settings.WHATSAPP_ACCESS_TOKEN or ""
        self.phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID or ""

    def is_configured(self) -> bool:
        return bool(self.access_token and self.phone_number_id)

    def _url(self, path: str) -> str:
        return f"{GRAPH_API_BASE}/{path}"

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}"}

    async def send_text(self, to: str, text: str, **kwargs) -> None:
        """Send a plain text message to a WhatsApp number (E.164)."""
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to.lstrip("+"),
            "type": "text",
            "text": {"body": text[:4096]},
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                self._url(f"{self.phone_number_id}/messages"),
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()

    async def send_interactive_buttons(
        self,
        to: str,
        body: str,
        buttons: list[dict],
        **kwargs,
    ) -> None:
        """
        Send interactive quick-reply buttons (max 3).
        buttons: [{"id": "approve", "title": "Approve"}, ...]
        title max 25 chars.
        """
        action_buttons = [
            {"type": "reply", "reply": {"id": b["id"], "title": b["title"][:25]}}
            for b in buttons[:3]
        ]
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to.lstrip("+"),
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body[:1024]},
                "action": {"buttons": action_buttons},
            },
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                self._url(f"{self.phone_number_id}/messages"),
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()

    async def download_media(self, msg: IncomingMessage) -> tuple[bytes, str]:
        """
        Download media file by ID.
        Returns (bytes, content_type).
        """
        media_id = msg.audio_id
        if not media_id:
            raise ValueError("WhatsApp download_media requires audio_id")
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            resp = await client.get(
                self._url(media_id),
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()
            url = data.get("url")
            if not url:
                raise ValueError(f"No url in media response: {data}")

            dl = await client.get(url, headers=self._headers())
            dl.raise_for_status()
            ct = dl.headers.get("content-type", "application/octet-stream")
            return dl.content, ct
