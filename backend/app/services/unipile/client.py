"""
Unipile API client for sending WhatsApp messages and fetching attachments.
Uses same patterns as Signalcore: respond_to_existing_chat, get_message_attachment.
"""

import logging
from typing import Optional

import httpx

from app.config import settings
from app.logging_config import log_domain, DOMAIN_UNIPILE
from app.metrics import inc_unipile_api_call
from app.services.whatsapp.webhook_parser import IncomingMessage

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
            logger.warning(
                "⚠️ Unipile send_text skipped: chat_id/account_id required",
                extra=log_domain(DOMAIN_UNIPILE, "send_skipped", to=to, chat_id=chat_id, account_id=account_id, reason="missing_chat_context"),
            )
            return

        url = f"{self.base_url.rstrip('/')}/api/v1/chats/{chat_id}/messages"
        payload = {"account_id": account_id, "text": text[:4096]}

        logger.info(
            "💬 Unipile send_text",
            extra=log_domain(DOMAIN_UNIPILE, "send_started", to=to, chat_id=chat_id, account_id=account_id),
        )
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    url,
                    data=payload,
                    headers=self._headers(),
                )
                resp.raise_for_status()
                inc_unipile_api_call("send_text", "success")
                logger.info(
                    "✅ Unipile send_text success",
                    extra=log_domain(DOMAIN_UNIPILE, "send_success", to=to, chat_id=chat_id, status=resp.status_code),
                )
        except httpx.HTTPStatusError as e:
            inc_unipile_api_call("send_text", "failure")
            logger.error(
                "❌ Unipile send_text failed",
                extra=log_domain(
                    DOMAIN_UNIPILE,
                    "send_failed",
                    to=to,
                    chat_id=chat_id,
                    status_code=e.response.status_code,
                    response_body=e.response.text[:500] if e.response.text else None,
                ),
                exc_info=True,
            )
            raise
        except Exception as e:
            inc_unipile_api_call("send_text", "failure")
            logger.error(
                "❌ Unipile send_text error",
                extra=log_domain(DOMAIN_UNIPILE, "send_failed", to=to, chat_id=chat_id, error=str(e)),
                exc_info=True,
            )
            raise

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
        Append compact reply instructions: approve:uuid or add:uuid.
        """
        if not chat_id or not account_id:
            logger.warning(
                "⚠️ Unipile send_interactive_buttons skipped: chat_id/account_id required",
                extra=log_domain(DOMAIN_UNIPILE, "send_buttons_skipped", to=to, reason="missing_chat_context"),
            )
            return

        # Short UX: "Reply 1 to approve, 2 to add fields" (no UUIDs)
        # Buttons may have id "1"/"2" or legacy "approve:uuid"/"add:uuid"
        approve_id = add_id = None
        for b in buttons[:3]:
            bid = (b.get("id") or "").strip()
            if bid.startswith("approve:") or bid == "1":
                approve_id = "1"
            elif bid.startswith("add:") or bid == "2":
                add_id = "2"

        footer_parts = []
        if approve_id:
            footer_parts.append("Reply 1 to approve")
        if add_id:
            footer_parts.append("2 to add fields")
        footer = ", or ".join(footer_parts) if footer_parts else ""

        full_text = f"{body}\n\n{footer}"[:4096] if footer else body[:4096]
        await self.send_text(to, full_text, chat_id=chat_id, account_id=account_id)

    async def download_media(self, msg: IncomingMessage) -> tuple[bytes, str]:
        """
        Fetch attachment from Unipile API.
        Requires msg.message_id and msg.audio_id (attachment_id).
        Returns (bytes, content_type).
        """
        if not msg.audio_id or not msg.message_id:
            raise ValueError("Unipile download_media requires message_id and audio_id")
        url = f"{self.base_url.rstrip('/')}/api/v1/messages/{msg.message_id}/attachments/{msg.audio_id}"
        logger.info(
            "📥 Unipile download_media",
            extra=log_domain(DOMAIN_UNIPILE, "download_started", message_id=msg.message_id, attachment_id=msg.audio_id),
        )
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.get(url, headers=self._headers())
                resp.raise_for_status()
                ct = resp.headers.get("content-type", "application/octet-stream")
                inc_unipile_api_call("download_media", "success")
                logger.info(
                    "✅ Unipile download_media success",
                    extra=log_domain(DOMAIN_UNIPILE, "download_success", message_id=msg.message_id, content_type=ct, size=len(resp.content)),
                )
                return resp.content, ct
        except Exception as e:
            inc_unipile_api_call("download_media", "failure")
            logger.error(
                "❌ Unipile download_media failed",
                extra=log_domain(DOMAIN_UNIPILE, "download_failed", message_id=msg.message_id, attachment_id=msg.audio_id, error=str(e)),
                exc_info=True,
            )
            raise
