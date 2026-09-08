"""Telnyx webhook authentication.

Telnyx signs ``timestamp|raw_body`` with Ed25519. The public key in Mission
Control may be hex or base64; try HexEncoder then Base64Encoder.
"""

from __future__ import annotations

import base64
import logging
import time

import nacl.encoding
import nacl.exceptions
import nacl.signing

logger = logging.getLogger(__name__)


def _normalize_public_key(public_key: str) -> str:
    key = (public_key or "").strip()
    if len(key) >= 2 and key[0] == key[-1] and key[0] in "\"'":
        key = key[1:-1].strip()
    return key


def _verify_key(public_key: str) -> nacl.signing.VerifyKey:
    try:
        return nacl.signing.VerifyKey(public_key, encoder=nacl.encoding.HexEncoder)
    except (ValueError, TypeError):
        return nacl.signing.VerifyKey(public_key, encoder=nacl.encoding.Base64Encoder)


def verify_telnyx_signature(
    *,
    public_key: str,
    timestamp: str,
    signature: str,
    raw_body: bytes,
    now: int | None = None,
    max_skew_seconds: int = 300,
) -> bool:
    public_key = _normalize_public_key(public_key)
    if not public_key or not timestamp or not signature or raw_body is None:
        return False
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False
    clock = now if now is not None else int(time.time())
    if abs(clock - ts) > max_skew_seconds:
        return False
    try:
        verify_key = _verify_key(public_key)
        verify_key.verify(
            f"{timestamp}|".encode("utf-8") + raw_body,
            base64.b64decode(signature),
        )
        return True
    except (nacl.exceptions.BadSignatureError, ValueError, TypeError) as exc:
        logger.warning("Telnyx signature validation error: %s", exc)
        return False
