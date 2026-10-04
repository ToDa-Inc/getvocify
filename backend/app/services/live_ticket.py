"""A short-lived pass for the live transcription service.

The live service runs apart from the main API so a busy API can never stall a call. It has no
session of its own: the signed-in app asks the main API for a ticket (POST
/transcription/ticket) and sends it as the first message on the live socket. The ticket names
the user and expires after a working day, so a long call can reconnect with it, and it never
appears in a URL or a log line. Signed with JWT_SECRET, which both services share.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from typing import Optional

from app.config import settings

TICKET_TTL_SECONDS = 12 * 3600


def _secret() -> bytes:
    secret = (settings.JWT_SECRET or "").encode()
    if not secret:
        raise RuntimeError("JWT_SECRET is not set")
    return secret


def _sign(payload: str) -> str:
    return hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()


def issue_ticket(user_id: str, *, now: Optional[float] = None) -> tuple[str, int]:
    """(ticket, expires_at epoch seconds) for this user."""
    expires = int((now if now is not None else time.time()) + TICKET_TTL_SECONDS)
    payload = base64.urlsafe_b64encode(f"{user_id}:{expires}".encode()).decode().rstrip("=")
    return f"{payload}.{_sign(payload)}", expires


def user_for_ticket(ticket: str, *, now: Optional[float] = None) -> Optional[str]:
    """The user a valid, unexpired ticket was issued to, else None."""
    try:
        payload, signature = ticket.rsplit(".", 1)
        if not hmac.compare_digest(signature, _sign(payload)):
            return None
        user_id, expires = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)).decode().rsplit(":", 1)
    except (ValueError, UnicodeDecodeError, RuntimeError):
        return None
    if int(expires) < (now if now is not None else time.time()) or not user_id:
        return None
    return user_id
