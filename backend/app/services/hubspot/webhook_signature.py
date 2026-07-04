"""
Validate HubSpot webhook signatures (v1 CRM webhooks and v3 HMAC).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time

from fastapi import Request

logger = logging.getLogger(__name__)

_URI_DECODE_MAP = (
    ("%3A", ":"),
    ("%2F", "/"),
    ("%3F", "?"),
    ("%40", "@"),
    ("%21", "!"),
    ("%24", "$"),
    ("%27", "'"),
    ("%28", "("),
    ("%29", ")"),
    ("%2A", "*"),
    ("%2C", ","),
    ("%3B", ";"),
)


def _normalize_uri_for_v3(uri: str) -> str:
    out = uri
    for enc, dec in _URI_DECODE_MAP:
        out = out.replace(enc, dec)
    return out


def verify_hubspot_webhook(request: Request, body: bytes, client_secret: str) -> bool:
    """Try v3 (X-HubSpot-Signature-v3 + timestamp) then v1 (sha256(secret + body))."""
    if not client_secret:
        return False

    body_str = body.decode("utf-8") if body else ""

    sig_v3 = request.headers.get("x-hubspot-signature-v3") or request.headers.get("X-HubSpot-Signature-v3")
    ts = request.headers.get("x-hubspot-request-timestamp") or request.headers.get("X-HubSpot-Request-Timestamp")
    if sig_v3 and ts:
        try:
            ts_ms = int(ts)
            now_ms = int(time.time() * 1000)
            if abs(now_ms - ts_ms) > 300_000:
                logger.warning("HubSpot webhook v3 timestamp outside 5m window")
                return False
        except ValueError:
            return False

        uri = _normalize_uri_for_v3(str(request.url))
        raw = f"{request.method.upper()}{uri}{body_str}{ts}"
        mac = hmac.new(
            client_secret.encode("utf-8"),
            raw.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        expected_b64 = base64.b64encode(mac).decode("utf-8")
        if hmac.compare_digest(expected_b64, sig_v3):
            return True
        logger.warning("HubSpot webhook v3 signature mismatch")

    sig_v1 = request.headers.get("x-hubspot-signature") or request.headers.get("X-HubSpot-Signature")
    if sig_v1:
        source = (client_secret + body_str).encode("utf-8")
        expected = hashlib.sha256(source).hexdigest()
        if hmac.compare_digest(expected, sig_v1):
            return True
        if hmac.compare_digest(expected.lower(), sig_v1.lower()):
            return True
        logger.warning("HubSpot webhook v1 signature mismatch")

    return False
