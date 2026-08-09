"""
Validate Unipile webhook signatures.

Unipile signs every webhook POST with:
    unipile-signature: t=<unix_seconds>,v0=<hex hmac-sha256>
computed as HMAC_SHA256(secret, f"{t}.{raw_body}"). Verifying this (and
rejecting stale timestamps) stops anyone who discovers the webhook URL from
injecting fake WhatsApp messages that get processed as if they were real.

See https://developer.unipile.com/v2.0/docs/configure-a-webhook
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time

logger = logging.getLogger(__name__)

_MAX_AGE_SECONDS = 300  # 5 minutes, same replay window HubSpot uses


def verify_unipile_webhook_signature(body: bytes, signature_header: str, secret: str) -> bool:
    if not secret or not signature_header:
        return False

    parts: dict[str, str] = {}
    for chunk in signature_header.split(","):
        if "=" not in chunk:
            continue
        key, _, value = chunk.strip().partition("=")
        parts[key.strip()] = value.strip()

    ts = parts.get("t")
    provided = parts.get("v0")
    if not ts or not provided:
        logger.warning("Unipile webhook signature header missing t/v0: %r", signature_header)
        return False

    try:
        ts_int = int(ts)
    except ValueError:
        return False
    if abs(time.time() - ts_int) > _MAX_AGE_SECONDS:
        logger.warning("Unipile webhook timestamp outside %ss window", _MAX_AGE_SECONDS)
        return False

    signed_payload = f"{ts}.".encode("utf-8") + body
    expected = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()

    if hmac.compare_digest(expected, provided):
        return True
    logger.warning("Unipile webhook signature mismatch")
    return False
