"""
Parse Unipile webhook payloads (direct or n8n-wrapped).
"""

import logging
import re
from typing import Any

from app.services.whatsapp.webhook_parser import IncomingMessage
from app.webhook_context import get_correlation_id, log_extra

logger = logging.getLogger(__name__)


def _extract_phone(body: dict) -> str | None:
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
    cid = get_correlation_id()

    event = body.get("event")
    if event != "message_received":
        logger.debug(
            "Unipile parse skip: event mismatch",
            extra=log_extra(message_id=body.get("message_id"), event=event, reason="event_not_message_received"),
        )
        return messages

    if body.get("account_type") != "WHATSAPP":
        logger.debug(
            "Unipile parse skip: account type",
            extra=log_extra(message_id=body.get("message_id"), account_type=body.get("account_type"), reason="account_type_not_whatsapp"),
        )
        return messages

    if body.get("is_sender"):
        logger.debug(
            "Unipile parse skip: is_sender",
            extra=log_extra(message_id=body.get("message_id"), reason="is_sender_true"),
        )
        return messages

    from_phone = _extract_phone(body)
    if not from_phone:
        sender_keys = list((body.get("sender") or {}).keys()) if isinstance(body.get("sender"), dict) else []
        logger.info(
            "Unipile parse skip: no phone extracted",
            extra=log_extra(
                message_id=body.get("message_id"),
                reason="no_phone_extracted",
                sender_keys=sender_keys,
            ),
        )
        return messages

    message_id = body.get("message_id") or ""
    timestamp = str(body.get("timestamp") or "")
    text = body.get("message") or ""
    chat_id = body.get("chat_id")
    account_id = body.get("account_id")

    # Detect button replies (approve:uuid, add:uuid) when user taps quick-reply
    bid = text.strip()
    msg_type = "text"
    button_id = None
    if bid.startswith("approve:") or bid.startswith("add:"):
        msg_type = "button"
        button_id = bid

    messages.append(
        IncomingMessage(
            message_id=message_id,
            from_phone=from_phone,
            timestamp=timestamp,
            type=msg_type,
            text=text if msg_type == "text" else None,
            button_id=button_id,
            chat_id=chat_id,
            account_id=account_id,
        )
    )
    if cid:
        logger.info(
            "Unipile parse ok",
            extra=log_extra(
                message_id=message_id,
                from_phone=from_phone,
                chat_id=chat_id,
                account_id=account_id,
                msg_type=msg_type,
            ),
        )
    return messages


def normalize_unipile_payload(body: Any) -> list[dict]:
    """
    Normalize incoming webhook body to list of Unipile event dicts.

    Handles:
    - n8n array format: [{ "body": { ... event ... } }]
    - Direct Unipile event: { "event": "message_received", ... }
    """
    cid = get_correlation_id()

    if isinstance(body, list):
        events = []
        for item in body:
            ev = item.get("body", item) if isinstance(item, dict) else item
            if isinstance(ev, dict) and ev.get("event"):
                events.append(ev)
        if not events and cid:
            logger.debug(
                "Unipile normalize: list had no valid events",
                extra=log_extra(reason="list_no_valid_events", list_len=len(body)),
            )
        return events

    if isinstance(body, dict) and body.get("event"):
        return [body]

    if cid:
        logger.debug(
            "Unipile normalize: unrecognized format",
            extra=log_extra(
                reason="unrecognized_format",
                body_type=type(body).__name__,
                top_keys=list(body.keys())[:10] if isinstance(body, dict) else None,
            ),
        )
    return []
