"""Send a follow-up draft from Vocify (D9), behind FOLLOWUP_SEND_ENABLED.

Separate from followup.py (which only drafts): this runs on the rep's explicit "Enviar",
never in the background, and its failures are the caller's to surface, not to log and move on.

Sending is claimed the same way followup.py leases a draft: an atomic conditional UPDATE
on memos.followup (PostgREST re-applies the filter to RETURNING, so an empty result does
not mean the claim was lost - ownership is confirmed by a read-by-PK afterwards), so two
concurrent requests for the same reviewed body never both call Resend.
"""
from __future__ import annotations

import hashlib
import html
import logging
import re
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.integrations.resend_client import ResendClientError, get_resend_client, get_resend_from_email

logger = logging.getLogger(__name__)

# How long a claim is allowed to sit in "sending" before another request may reclaim it
# (a crashed or hung request should not wedge a memo forever).
SEND_STALE = timedelta(minutes=2)

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")
_UNSAFE_DISPLAY_CHARS_RE = re.compile(r'[<>",;]')

RATE_LIMIT_MAX = 20  # follow-ups a rep may send from Vocify per hour
RATE_LIMIT_WINDOW = timedelta(hours=1)
_rate_lock = threading.Lock()
_sends_by_rep: dict[str, list[datetime]] = {}


def send_hash(subject: str, body: str) -> str:
    """Identifies one reviewed body: same subject+body, same hash. A rep edit changes it,
    so a resend after an edit is not mistaken for the same send (idempotent by revision)."""
    return hashlib.sha256(f"{subject}\n{body}".encode("utf-8")).hexdigest()


def _first(result: Any) -> Optional[dict]:
    rows = getattr(result, "data", None) or []
    return rows[0] if rows and isinstance(rows[0], dict) else None


def claim_send(supabase: Any, memo_id: str, current: dict, revision: str, run_id: str, now: datetime) -> tuple[str, dict]:
    """Atomically claims sending this exact reviewed revision.

    Returns ("claimed", followup) when this call now owns it and must send, or
    ("busy", followup) when another call already holds a fresh claim or has already sent
    it - the caller must not call Resend again and should just report that state.
    """
    cutoff = (now - SEND_STALE).isoformat()
    claimed = {
        **current,
        "vocify_send_hash": revision,
        "vocify_send_state": "sending",
        "vocify_send_run_id": run_id,
        "vocify_sending_started_at": now.isoformat(),
    }
    q = supabase.table("memos").update({"followup": claimed}).eq("id", memo_id)
    if hasattr(q, "or_"):
        # Allowed to (re)claim when: this is a new revision, or the existing claim on this
        # same revision failed, or is stale. Never when it is fresh "sending" or "sent".
        q = q.or_(
            f"followup->>vocify_send_hash.neq.{revision},"
            "followup->>vocify_send_state.eq.failed,"
            "followup->>vocify_send_state.is.null,"
            f"followup->>vocify_sending_started_at.lt.{cutoff}"
        )
    q.execute()
    row = _first(supabase.table("memos").select("followup").eq("id", memo_id).limit(1).execute())
    followup = (row or {}).get("followup") or current
    won = bool(row) and followup.get("vocify_send_run_id") == run_id
    return ("claimed" if won else "busy"), followup


def finish_send(supabase: Any, memo_id: str, run_id: str, followup: dict) -> None:
    """Writes the outcome of a claimed send, but only while this call still owns the claim
    (a reclaimed-as-stale send is not ours to overwrite)."""
    (
        supabase.table("memos")
        .update({"followup": followup})
        .eq("id", memo_id)
        .eq("followup->>vocify_send_run_id", run_id)
        .execute()
    )


def reset_rate_limit() -> None:
    """Test-only: clears the in-process per-rep counters."""
    with _rate_lock:
        _sends_by_rep.clear()


def rate_limited(user_id: str, *, now: Optional[datetime] = None) -> bool:
    """A simple in-process per-rep cap: True once this rep has already sent
    RATE_LIMIT_MAX follow-ups from Vocify in the last hour."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - RATE_LIMIT_WINDOW
    with _rate_lock:
        recent = [sent_at for sent_at in _sends_by_rep.get(user_id, []) if sent_at > cutoff]
        if len(recent) >= RATE_LIMIT_MAX:
            _sends_by_rep[user_id] = recent
            return True
        recent.append(now)
        _sends_by_rep[user_id] = recent
        return False


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


def _sanitize_display_name(name: str) -> str:
    """A CRM/profile full_name is untrusted input landing in an email header: drop control
    characters and the characters that let it break out of the display-name/address pair
    (<, >, quotes, comma, semicolon) before it is ever quoted into a From header."""
    cleaned = _CONTROL_CHARS_RE.sub("", name)
    cleaned = _UNSAFE_DISPLAY_CHARS_RE.sub("", cleaned)
    return cleaned.strip()


def _clean_subject(subject: str) -> str:
    """Collapses embedded CR/LF (header injection) and surrounding whitespace to one line."""
    return " ".join((subject or "").split())


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
    """D9: from is "{rep_name} vía Vocify" (quoted, sanitized), reply_to is the rep's own
    mailbox."""
    client = get_resend_client()
    if client is None:
        return {"ok": False, "error": "resend_not_configured"}
    safe_name = _sanitize_display_name(rep_name) if rep_name else ""
    display = f"{safe_name} vía Vocify" if safe_name else "Vocify"
    from_email = get_resend_from_email(f'"{display}"')
    try:
        result = await client.send_email(
            to,
            _clean_subject(subject) or "Seguimiento",
            body_to_html(body),
            from_email=from_email,
            idempotency_key=idempotency_key,
            reply_to=rep_email,
        )
    except ResendClientError as exc:
        logger.warning("followup send: Resend error: %s", exc)
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "email_id": (result or {}).get("id") if isinstance(result, dict) else None}
