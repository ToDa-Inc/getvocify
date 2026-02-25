"""
Parse Unipile webhook payloads (direct or n8n-wrapped).
"""

import logging
import re
from typing import Any, Optional

from app.logging_config import log_domain, DOMAIN_UNIPILE
from app.services.whatsapp.webhook_parser import IncomingMessage

logger = logging.getLogger(__name__)


def _extract_phone(body: dict) -> Optional[str]:
    """Extract sender phone from Unipile event body."""
    sender = body.get("sender") or {}
    specifics = sender.get("attendee_specifics") or {}
    phone = specifics.get("phone_number")
    if phone:
        return _normalize_phone(phone)

    # Fallback: parse from attendee_public_identifier or provider_chat_id
    for key in ("attendee_public_identifier", "provider_chat_id"):
        val = body.get(key) or (sender.get(key) if isinstance(sender, dict) else None)
        if val and "@" in str(val):
            prefix = str(val).split("@")[0]
            digits = re.sub(r"\D", "", prefix)
            if digits:
                return f"+{digits}"
    return None


def _normalize_phone(phone: str) -> str:
    """Normalize to E.164-ish: digits only, leading + for lookup."""
    digits = re.sub(r"\D", "", phone)
    return f"+{digits}" if digits and not digits.startswith("+") else digits or ""


def parse_unipile_webhook(body: dict) -> list[IncomingMessage]:
    """
    Extract messages from a single Unipile event body.

    Expects the raw Unipile event (event, account_id, sender, message, etc.)
    or a structure with those keys. Returns list of IncomingMessage.
    """
    messages: list[IncomingMessage] = []

    event = body.get("event")
    if event != "message_received":
        logger.info(
            "Unipile parse skip: event mismatch",
            extra=log_domain(DOMAIN_UNIPILE, "parse_skip", message_id=body.get("message_id"), event=event, reason="event_not_message_received"),
        )
        return messages

    if body.get("account_type") != "WHATSAPP":
        logger.info(
            "Unipile parse skip: account type",
            extra=log_domain(DOMAIN_UNIPILE, "parse_skip", message_id=body.get("message_id"), account_type=body.get("account_type"), reason="account_type_not_whatsapp"),
        )
        return messages

    if body.get("is_sender"):
        logger.info(
            "Unipile parse skip: is_sender",
            extra=log_domain(DOMAIN_UNIPILE, "parse_skip", message_id=body.get("message_id"), reason="is_sender_true"),
        )
        return messages

    from_phone = _extract_phone(body)
    if not from_phone:
        sender_keys = list((body.get("sender") or {}).keys()) if isinstance(body.get("sender"), dict) else []
        logger.info(
            "Unipile parse skip: no phone extracted",
            extra=log_domain(DOMAIN_UNIPILE, "parse_skip", message_id=body.get("message_id"), reason="no_phone_extracted", sender_keys=sender_keys),
        )
        return messages

    message_id = body.get("message_id") or ""
    timestamp = str(body.get("timestamp") or "")
    text = body.get("message") or ""
    chat_id = body.get("chat_id")
    account_id = body.get("account_id")
    attachments = body.get("attachments") or []

    # Detect audio attachment (voice note or audio)
    audio_attachment = None
    for att in attachments if isinstance(attachments, list) else []:
        a = att if isinstance(att, dict) else {}
        if a.get("attachment_type") == "audio" or a.get("voice_note"):
            audio_attachment = a
            break

    # Determine message type: text or audio
    # Text is always type="text" - intent (approve/add) resolved via conversation state
    msg_type = "text"
    button_id = None
    audio_id = None
    audio_mime = None

    if audio_attachment:
        msg_type = "audio"
        audio_id = audio_attachment.get("attachment_id")

    messages.append(
        IncomingMessage(
            message_id=message_id,
            from_phone=from_phone,
            timestamp=timestamp,
            type=msg_type,
            text=text if msg_type == "text" else None,
            audio_id=audio_id,
            audio_mime=audio_mime,
            button_id=button_id,
            chat_id=chat_id,
            account_id=account_id,
        )
    )
    logger.info(
        "Unipile parse ok",
        extra=log_domain(DOMAIN_UNIPILE, "parse_ok", message_id=message_id, from_phone=from_phone, chat_id=chat_id, account_id=account_id, msg_type=msg_type, has_audio_id=bool(audio_id)),
    )
    return messages


def normalize_unipile_payload(body: Any) -> list[dict]:
    """
    Normalize incoming webhook body to list of Unipile event dicts.

    Handles:
    - n8n array format: [{ "body": { ... event ... } }]
    - Direct Unipile event: { "event": "message_received", ... }
    """
    if isinstance(body, list):
        events = []
        for item in body:
            ev = item.get("body", item) if isinstance(item, dict) else item
            if isinstance(ev, dict) and ev.get("event"):
                events.append(ev)
        if not events:
            logger.info(
                "Unipile normalize: list had no valid events",
                extra=log_domain(DOMAIN_UNIPILE, "normalize_skip", reason="list_no_valid_events", list_len=len(body)),
            )
        return events

    if isinstance(body, dict) and body.get("event"):
        return [body]

    logger.info(
        "Unipile normalize: unrecognized format",
        extra=log_domain(DOMAIN_UNIPILE, "normalize_skip", reason="unrecognized_format", body_type=type(body).__name__, top_keys=list(body.keys())[:10] if isinstance(body, dict) else None),
    )
    return []
