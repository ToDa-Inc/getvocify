"""Twilio webhook authentication.

Twilio signs the exact URL it requested plus the sorted POST params. Behind a
proxy the request URL seen by FastAPI can differ from the public one, so the
caller must rebuild the URL from BACKEND_PUBLIC_URL rather than trusting
`request.url`.
"""

from __future__ import annotations

import logging
from typing import Optional

from twilio.request_validator import RequestValidator

logger = logging.getLogger(__name__)

CLIENT_PREFIX = "client:"


def verify_twilio_signature(
    url: str,
    params: dict[str, str],
    signature: str,
    auth_token: str,
) -> bool:
    if not signature or not auth_token:
        return False
    try:
        return bool(RequestValidator(auth_token).validate(url, params, signature))
    except Exception as e:  # malformed signature header
        logger.warning("Twilio signature validation error: %s", e)
        return False


def identity_from_client_from(from_value: str) -> Optional[str]:
    """`From=client:<identity>` on calls originated by a Voice SDK client."""
    value = (from_value or "").strip()
    if not value.startswith(CLIENT_PREFIX):
        return None
    identity = value[len(CLIENT_PREFIX):].strip()
    return identity or None
