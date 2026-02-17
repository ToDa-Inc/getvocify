"""
Parse incoming WhatsApp Cloud API webhook payloads.
"""

from dataclasses import dataclass
from typing import Literal, Optional


@dataclass
class IncomingMessage:
    """Parsed incoming WhatsApp message."""

    message_id: str
    from_phone: str
    timestamp: str
    type: Literal["text", "audio", "button"]
    text: Optional[str] = None
    audio_id: Optional[str] = None
    audio_mime: Optional[str] = None
    button_id: Optional[str] = None
    button_title: Optional[str] = None
    context_message_id: Optional[str] = None


def parse_webhook(payload: dict) -> list[IncomingMessage]:
    """
    Extract messages from webhook payload.
    Returns list of IncomingMessage (typically one per webhook call).
    """
    messages: list[IncomingMessage] = []
    try:
        entries = payload.get("entry", [])
        for entry in entries:
            changes = entry.get("changes", [])
            for change in changes:
                val = change.get("value", {})
                msgs = val.get("messages", [])
                for m in msgs:
                    msg_id = m.get("id", "")
                    from_phone = str(m.get("from", ""))
                    ts = str(m.get("timestamp", ""))

                    if m.get("type") == "text":
                        body = (m.get("text") or {}).get("body", "")
                        messages.append(
                            IncomingMessage(
                                message_id=msg_id,
                                from_phone=from_phone,
                                timestamp=ts,
                                type="text",
                                text=body,
                            )
                        )
                    elif m.get("type") == "audio":
                        audio = m.get("audio") or {}
                        messages.append(
                            IncomingMessage(
                                message_id=msg_id,
                                from_phone=from_phone,
                                timestamp=ts,
                                type="audio",
                                audio_id=audio.get("id"),
                                audio_mime=audio.get("mime_type"),
                            )
                        )
                    elif m.get("type") == "interactive":
                        interactive = m.get("interactive") or {}
                        if interactive.get("type") == "button_reply":
                            reply = interactive.get("button_reply") or {}
                            context = m.get("context") or {}
                            messages.append(
                                IncomingMessage(
                                    message_id=msg_id,
                                    from_phone=from_phone,
                                    timestamp=ts,
                                    type="button",
                                    button_id=reply.get("id"),
                                    button_title=reply.get("title"),
                                    context_message_id=context.get("id"),
                                )
                            )
    except Exception:
        pass
    return messages
