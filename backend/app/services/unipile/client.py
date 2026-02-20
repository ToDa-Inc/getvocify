"""
Unipile API client for sending WhatsApp messages.
Uses same patterns as Signalcore: respond_to_existing_chat (FormData).
"""

import logging
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class UnipileClient:
    """
    Unipile API client for sending messages.
    Requires chat_id and account_id from the incoming webhook to reply.
    """

    def __init__(self) -> None:
        self.api_key = settings.UNIPILE_API_KEY or ""
        base = (settings.UNIPILE_BASE_URL or "").strip()
        if base and not base.startswith("http"):
            base = f"https://{base}"
        self.base_url = base or "https://api.unipile.com"

    def is_configured(self) -> bool:
        return bool(self.api_key and self.base_url)

    def _headers(self) -> dict:
        return {
            "X-API-KEY": self.api_key,
            "accept": "application/json",
        }

    async def send_text(
        self,
        to: str,
        text: str,
        *,
        chat_id: Optional[str] = None,
        account_id: Optional[str] = None,
        **kwargs,
    ) -> None:
        """
        Send a text message. For Unipile, chat_id and account_id are required.
        """
        if not chat_id or not account_id:
            logger.warning("Unipile send_text: chat_id and account_id required, skipping")
            return

        url = f"{self.base_url.rstrip('/')}/api/v1/chats/{chat_id}/messages"
        payload = {"account_id": account_id, "text": text[:4096]}

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                url,
                data=payload,
                headers=self._headers(),
            )
            resp.raise_for_status()

    async def send_interactive_buttons(
        self,
        to: str,
        body: str,
        buttons: list[dict],
        *,
        chat_id: Optional[str] = None,
        account_id: Optional[str] = None,
        **kwargs,
    ) -> None:
        """
        Unipile does not support Meta-style interactive buttons.
        Append reply commands so user can reply 'approve:id' or 'add:id'.
        """
        if not chat_id or not account_id:
            logger.warning("Unipile send_interactive_buttons: chat_id and account_id required, skipping")
            return

        lines = [body, ""]
        for b in buttons[:3]:
            bid = b.get("id", "")
            title = b.get("title", "") or bid
            if bid:
                lines.append(f"{title}: reply '{bid}'")
        full_text = "\n".join(lines)[:4096]

        await self.send_text(to, full_text, chat_id=chat_id, account_id=account_id)
