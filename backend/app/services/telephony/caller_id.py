"""Verified caller IDs: the SDR's own number, presented on outbound calls.

Twilio's Transit Caller ID was sunset on 2026-06-22, so a Verified Caller ID
(or a Twilio-owned number) is the only supported way to present a number.
Twilio performs the ownership proof; `user_caller_ids` records the outcome so
the voice webhook can authorize a caller ID without a round trip.

The verification call/SMS is placed by Twilio and is English-only, so the UI
must surface `verificationCode` to the user.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from supabase import Client

from app.config import settings
from app.services.telephony.twilio_client import twilio_rest
from app.services.telephony.twiml import normalize_e164

logger = logging.getLogger(__name__)


class CallerIdNotVerified(PermissionError):
    """The requested caller ID is not a verified number for this user."""


def _status_callback_url() -> str:
    base = (settings.BACKEND_PUBLIC_URL or "").rstrip("/")
    return f"{base}/webhooks/twilio/caller-id-status"


def start_caller_id_verification(
    supabase: Client,
    user_id: str,
    raw_number: str,
    label: Optional[str],
) -> dict[str, Any]:
    """Ask Twilio to verify a number and return the code the user must enter."""
    phone_number = normalize_e164(
        raw_number, default_country_code=settings.CALLING_DEFAULT_COUNTRY_CODE
    )

    existing_rows = (
        supabase.table("user_caller_ids")
        .select("phone_number,status,label,twilio_validation_sid,verified_at")
        .eq("user_id", user_id)
        .eq("phone_number", phone_number)
        .limit(1)
        .execute()
        .data
    ) or []
    if existing_rows and existing_rows[0].get("status") == "verified":
        row = existing_rows[0]
        return {
            "phoneNumber": phone_number,
            "status": "verified",
            "validationSid": row.get("twilio_validation_sid"),
            "alreadyVerified": True,
        }

    validation = twilio_rest().validation_requests.create(
        phone_number=phone_number,
        friendly_name=(label or f"Vocify {phone_number}")[:64],
        status_callback=_status_callback_url(),
    )

    upsert_row: dict[str, Any] = {
        "user_id": user_id,
        "phone_number": phone_number,
        "status": "pending",
        "twilio_validation_sid": validation.call_sid,
        "verified_at": None,
    }
    if label is not None:
        upsert_row["label"] = label

    supabase.table("user_caller_ids").upsert(
        upsert_row,
        on_conflict="user_id,phone_number",
    ).execute()

    return {
        "phoneNumber": phone_number,
        "verificationCode": validation.validation_code,
        "status": "pending",
        "validationSid": validation.call_sid,
        "alreadyVerified": False,
    }


def _set_status(
    supabase: Client, twilio_validation_sid: Optional[str], status: str
) -> bool:
    if not twilio_validation_sid:
        logger.warning(
            "caller ID status callback missing twilio_validation_sid (CallSid); "
            "leaving row pending"
        )
        return False
    update: dict[str, Any] = {"status": status}
    if status == "verified":
        update["verified_at"] = datetime.now(timezone.utc).isoformat()
    res = (
        supabase.table("user_caller_ids")
        .update(update)
        .eq("twilio_validation_sid", twilio_validation_sid)
        .execute()
    )
    return bool(res.data)


def mark_caller_id_verified(
    supabase: Client, twilio_validation_sid: Optional[str]
) -> bool:
    return _set_status(supabase, twilio_validation_sid, "verified")


def mark_caller_id_failed(
    supabase: Client, twilio_validation_sid: Optional[str]
) -> bool:
    return _set_status(supabase, twilio_validation_sid, "failed")


def list_caller_ids(supabase: Client, user_id: str) -> list[dict[str, Any]]:
    res = (
        supabase.table("user_caller_ids")
        .select("phone_number,status,label,is_default,verified_at")
        .eq("user_id", user_id)
        .order("created_at")
        .execute()
    )
    return [
        {
            "phoneNumber": row.get("phone_number"),
            "status": row.get("status"),
            "label": row.get("label"),
            "isDefault": bool(row.get("is_default")),
            "verifiedAt": row.get("verified_at"),
        }
        for row in (res.data or [])
    ]


def resolve_caller_id(
    supabase: Client,
    user_id: str,
    requested: Optional[str],
) -> str:
    """Authorize a caller ID for this user, or raise.

    The browser client sends a preference; this is the only place that decides.
    A client must never be able to present a number it does not own.
    """
    query = (
        supabase.table("user_caller_ids")
        .select("phone_number,status")
        .eq("user_id", user_id)
        .eq("status", "verified")
    )
    if requested:
        query = query.eq("phone_number", requested)
    else:
        query = query.order("is_default", desc=True)

    rows = (query.limit(1).execute().data) or []
    verified = [r for r in rows if (r.get("status") == "verified")]
    if not verified:
        raise CallerIdNotVerified(
            f"no verified caller ID for user {user_id} (requested={requested!r})"
        )
    return str(verified[0]["phone_number"])
