"""
Validate Meta (WhatsApp Cloud API) webhook signatures.

Meta signs every webhook POST with X-Hub-Signature-256: sha256=<hex hmac>,
computed over the raw request body using the App Secret. Without checking
this, anyone who discovers the webhook URL can POST arbitrary payloads that
get processed as if they were real WhatsApp messages.
"""

from __future__ import annotations

import hashlib
import hmac
import logging

logger = logging.getLogger(__name__)


def verify_meta_webhook_signature(body: bytes, signature_header: str, app_secret: str) -> bool:
    """
    Verify X-Hub-Signature-256 (falls back to legacy X-Hub-Signature/sha1 if that's
    what's present) against the raw request body.
    """
    if not app_secret or not signature_header:
        return False

    header = signature_header.strip()
    if "=" not in header:
        return False
    algo, _, provided = header.partition("=")
    algo = algo.strip().lower()

    if algo == "sha256":
        digest = hmac.new(app_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    elif algo == "sha1":
        digest = hmac.new(app_secret.encode("utf-8"), body, hashlib.sha1).hexdigest()
    else:
        logger.warning("Unsupported WhatsApp webhook signature algorithm: %s", algo)
        return False

    if hmac.compare_digest(digest, provided.strip()):
        return True
    logger.warning("WhatsApp webhook signature mismatch")
    return False
