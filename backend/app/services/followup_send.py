"""Send a follow-up draft from Vocify (D9), behind FOLLOWUP_SEND_ENABLED.

Separate from followup.py (which only drafts): this runs on the rep's explicit "Enviar",
never in the background, and its failures are the caller's to surface, not to log and move on.
"""
from __future__ import annotations

import hashlib
import html
import logging
from typing import Any, Optional

from app.integrations.resend_client import ResendClientError, get_resend_client, get_resend_from_email

logger = logging.getLogger(__name__)


def send_hash(subject: str, body: str) -> str:
    """Identifies one reviewed body: same subject+body, same hash. A rep edit changes it,
    so a resend after an edit is not mistaken for the same send (idempotent by revision)."""
    return hashlib.sha256(f"{subject}\n{body}".encode("utf-8")).hexdigest()


def rep_identity(supabase: Any, user_id: str) -> tuple[Optional[str], Optional[str]]:
    """The rep's display name (for the "from") and mailbox (for reply_to)."""
    name: Optional[str] = None
    try:
        rows = (
            supabase.table("user_profiles").select("full_name").eq("id", user_id).limit(1).execute().data or []
        )
        name = (rows[0] or {}).get("full_name") if rows else None
    except Exception as exc:
        logger.warning("followup send: could not load rep name for %s: %s", user_id, exc)

    email: Optional[str] = None
    try:
        user = supabase.auth.admin.get_user_by_id(user_id)
        if isinstance(user, dict):
            email = user.get("email")
        else:
            email = getattr(user, "email", None)
            nested = getattr(user, "user", None)
            if not email and nested is not None:
                email = getattr(nested, "email", None)
    except Exception as exc:
        logger.warning("followup send: could not load rep email for %s: %s", user_id, exc)
    return name, (email or None)


def body_to_html(body: str) -> str:
    """The plain-text draft, escaped and paragraph-wrapped, as Resend expects."""
    paragraphs = [p.strip() for p in (body or "").split("\n\n") if p.strip()]
    if not paragraphs:
        return html.escape(body or "")
    return "".join(f"<p>{html.escape(p).replace(chr(10), '<br>')}</p>" for p in paragraphs)


async def send_followup_email(
    *,
    to: str,
    subject: str,
    body: str,
    rep_name: Optional[str],
    rep_email: Optional[str],
    idempotency_key: str,
) -> dict:
    """D9: from is "{rep_name} vía Vocify", reply_to is the rep's own mailbox."""
    client = get_resend_client()
    if client is None:
        return {"ok": False, "error": "resend_not_configured"}
    display = f"{rep_name} vía Vocify" if rep_name else "Vocify"
    from_email = get_resend_from_email(display)
    try:
        result = await client.send_email(
            to,
            subject.strip() or "Seguimiento",
            body_to_html(body),
            from_email=from_email,
            idempotency_key=idempotency_key,
            reply_to=rep_email,
        )
    except ResendClientError as exc:
        logger.warning("followup send: Resend error: %s", exc)
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "email_id": (result or {}).get("id") if isinstance(result, dict) else None}
