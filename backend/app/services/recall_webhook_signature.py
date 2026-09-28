"""Validate Recall.ai webhook signatures.

Recall signs webhooks the Svix way: `webhook-id`, `webhook-timestamp` and
`webhook-signature` headers, with a secret prefixed `whsec_` (base64 after that
prefix). The signed content is `{id}.{timestamp}.{raw_body}`, HMAC-SHA256'd with
the decoded secret and base64-encoded. `webhook-signature` can carry several
space-separated `v1,<sig>` tokens (key rotation); any one matching is enough.
Without this check, anyone who finds the webhook URL could POST a fake
`bot.done` and have its "transcript" written into a real capture.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time

logger = logging.getLogger(__name__)

_MAX_AGE_SECONDS = 300  # 5 minutes, same replay window HubSpot/Unipile use


def _secret_bytes(secret: str) -> bytes:
    raw = secret[len("whsec_"):] if secret.startswith("whsec_") else secret
    try:
        return base64.b64decode(raw)
    except Exception:
        return raw.encode("utf-8")


def verify_recall_webhook_signature(
    *,
    webhook_id: str,
    webhook_timestamp: str,
    signature_header: str,
    body: bytes,
    secret: str,
) -> bool:
    if not secret or not signature_header or not webhook_id or not webhook_timestamp:
        return False

    try:
        ts_int = int(webhook_timestamp)
    except ValueError:
        return False
    if abs(time.time() - ts_int) > _MAX_AGE_SECONDS:
        logger.warning("Recall webhook timestamp outside %ss window", _MAX_AGE_SECONDS)
        return False

    signed_content = f"{webhook_id}.{webhook_timestamp}.".encode("utf-8") + body
    expected = base64.b64encode(
        hmac.new(_secret_bytes(secret), signed_content, hashlib.sha256).digest()
    ).decode("ascii")

    for token in signature_header.split():
        _, _, candidate = token.partition(",")
        candidate = candidate or token
        if hmac.compare_digest(candidate, expected):
            return True
    logger.warning("Recall webhook signature mismatch")
    return False
