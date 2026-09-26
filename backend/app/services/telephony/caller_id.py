"""Verified caller IDs: the SDR's own number, presented on outbound calls.

Twilio's Transit Caller ID was sunset on 2026-06-22. Outbound CLI is only a
number the user has verified with Twilio; rented Twilio DIDs are not offered
as a From identity.

Twilio performs the ownership proof; `user_caller_ids` records the outcome so
the voice webhook can authorize a caller ID without a round trip.

The verification call is placed by Twilio and is English-only, so the UI
must surface `verificationCode` to the user.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Literal, Optional
from zoneinfo import ZoneInfo

from supabase import Client

from app.config import settings
from twilio.base.exceptions import TwilioRestException

from app.services.telephony.provider import calling_provider
from app.services.telephony.telnyx_client import telnyx_rest
from app.services.telephony.twilio_client import twilio_rest
from app.services.telephony.twiml import normalize_e164

logger = logging.getLogger(__name__)


class CallerIdNotVerified(PermissionError):
    """The requested caller ID is not a verified number for this user."""


class CallerIdVerificationUnsupported(RuntimeError):
    """Twilio region cannot verify personal caller IDs (IE1)."""


class CallerIdRangeRestricted(CallerIdNotVerified):
    """The number is in a Spanish range that cannot present commercial calls."""


IE1_VERIFIED_CALLER_ID_MESSAGE = (
    "Twilio en Irlanda (IE1) no permite Verified Caller IDs. "
    "Usa una cuenta Twilio en US1 para verificar tu número."
)

ES_MOBILE_CALLER_ID_MESSAGE = (
    "Los móviles españoles no pueden usarse para llamadas comerciales "
    "(Orden TDF/149/2025, art. 9). Usa un fijo."
)
ES_400_CALLER_ID_MESSAGE = (
    "Los números 400 no reciben llamadas, así que no se pueden verificar."
)
ES_MOBILE_CALL_BLOCKED_SPOKEN = (
    "Tu identificador es un móvil español y no se puede usar para llamadas "
    "comerciales. Elige un fijo en Ajustes."
)

SpanishCliRestriction = Literal["es_mobile", "es_400"]

_ES_MOBILE_PREFIXES = ("+346", "+347")
_ES_400_PREFIX = "+34400"
_MADRID = ZoneInfo("Europe/Madrid")


def spanish_cli_restriction(phone_number: str) -> Optional[SpanishCliRestriction]:
    """Classify an E.164 number against the Spanish commercial-CLI rules."""
    if phone_number.startswith(_ES_400_PREFIX):
        return "es_400"
    if phone_number.startswith(_ES_MOBILE_PREFIXES):
        return "es_mobile"
    return None


def _today_madrid() -> date:
    return datetime.now(_MADRID).date()


def _gate_enabled() -> bool:
    return bool(settings.CALLING_ES_CLI_GATE_ENABLED)


def _mobile_call_blocked(phone_number: str, today: date) -> bool:
    return (
        _gate_enabled()
        and spanish_cli_restriction(phone_number) == "es_mobile"
        and today >= settings.CALLING_ES_MOBILE_CALL_BLOCK_FROM
    )


def _ensure_verifiable(phone_number: str) -> None:
    if not _gate_enabled():
        return
    restriction = spanish_cli_restriction(phone_number)
    if restriction == "es_mobile":
        raise CallerIdRangeRestricted(ES_MOBILE_CALLER_ID_MESSAGE)
    if restriction == "es_400":
        raise CallerIdRangeRestricted(ES_400_CALLER_ID_MESSAGE)


def _caller_id_notice(phone_number: str, today: date) -> Optional[str]:
    if not _gate_enabled() or spanish_cli_restriction(phone_number) != "es_mobile":
        return None
    if _mobile_call_blocked(phone_number, today):
        return ES_MOBILE_CALLER_ID_MESSAGE
    block_from = settings.CALLING_ES_MOBILE_CALL_BLOCK_FROM
    return (
        f"Móvil español: dejará de poder llamar el {block_from:%d/%m/%Y}. "
        "Añade un fijo."
    )


def _status_callback_url() -> str:
    base = (settings.BACKEND_PUBLIC_URL or "").rstrip("/")
    return f"{base}/webhooks/twilio/caller-id-status"


def _telnyx_verification_sid(payload: Any, phone_number: str) -> str:
    data = payload.get("data") if isinstance(payload, dict) else None
    source = data if isinstance(data, dict) else payload if isinstance(payload, dict) else {}
    vid = source.get("id")
    return str(vid) if vid else phone_number


def start_caller_id_verification(
    supabase: Client,
    user_id: str,
    raw_number: str,
    label: Optional[str],
) -> dict[str, Any]:
    """Start provider verification. Twilio returns a keypad code; Telnyx sends OTP."""
    phone_number = normalize_e164(
        raw_number, default_country_code=settings.CALLING_DEFAULT_COUNTRY_CODE
    )
    _ensure_verifiable(phone_number)

    existing_rows = (
        supabase.table("user_caller_ids")
        .select("phone_number,status,label,verification_sid,verified_at")
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
            "validationSid": row.get("verification_sid"),
            "alreadyVerified": True,
        }

    if calling_provider() == "telnyx":
        payload = telnyx_rest().create_verified_number(phone_number)
        verification_sid = _telnyx_verification_sid(payload, phone_number)
        upsert_row: dict[str, Any] = {
            "user_id": user_id,
            "phone_number": phone_number,
            "status": "pending",
            "verification_sid": verification_sid,
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
            "status": "pending",
            "needsCodeSubmit": True,
            "alreadyVerified": False,
        }

    try:
        validation = twilio_rest().validation_requests.create(
            phone_number=phone_number,
            friendly_name=(label or f"Vocify {phone_number}")[:64],
            status_callback=_status_callback_url(),
        )
    except TwilioRestException as exc:
        if getattr(exc, "status", None) == 405:
            raise CallerIdVerificationUnsupported(
                IE1_VERIFIED_CALLER_ID_MESSAGE
            ) from exc
        if _twilio_already_verified(exc):
            return _claim_twilio_verified_number(
                supabase, user_id, phone_number, label
            )
        raise

    upsert_row: dict[str, Any] = {
        "user_id": user_id,
        "phone_number": phone_number,
        "status": "pending",
        "verification_sid": validation.call_sid,
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


def confirm_caller_id_verification(
    supabase: Client,
    user_id: str,
    raw_number: str,
    code: str,
) -> dict[str, Any]:
    """Submit the Telnyx OTP and mark the number verified for this user."""
    phone_number = normalize_e164(
        raw_number, default_country_code=settings.CALLING_DEFAULT_COUNTRY_CODE
    )
    _ensure_verifiable(phone_number)
    existing = (
        supabase.table("user_caller_ids")
        .select("phone_number")
        .eq("user_id", user_id)
        .eq("phone_number", phone_number)
        .limit(1)
        .execute()
        .data
    ) or []
    if not existing:
        raise CallerIdNotVerified(
            f"no caller ID row for user {user_id} ({phone_number})"
        )
    telnyx_rest().verify_number_code(phone_number, code)
    now = datetime.now(timezone.utc).isoformat()
    res = (
        supabase.table("user_caller_ids")
        .update({"status": "verified", "verified_at": now})
        .eq("user_id", user_id)
        .eq("phone_number", phone_number)
        .execute()
    )
    if not res.data:
        raise CallerIdNotVerified(
            f"no caller ID row for user {user_id} ({phone_number})"
        )
    return {
        "phoneNumber": phone_number,
        "status": "verified",
        "alreadyVerified": False,
    }


def _set_status(
    supabase: Client, verification_sid: Optional[str], status: str
) -> bool:
    if not verification_sid:
        logger.warning(
            "caller ID status callback missing verification_sid (CallSid); "
            "leaving row pending"
        )
        return False
    update: dict[str, Any] = {"status": status}
    if status == "verified":
        update["verified_at"] = datetime.now(timezone.utc).isoformat()
    res = (
        supabase.table("user_caller_ids")
        .update(update)
        .eq("verification_sid", verification_sid)
        .execute()
    )
    return bool(res.data)


def mark_caller_id_verified(
    supabase: Client, verification_sid: Optional[str]
) -> bool:
    return _set_status(supabase, verification_sid, "verified")


def mark_caller_id_failed(
    supabase: Client, verification_sid: Optional[str]
) -> bool:
    return _set_status(supabase, verification_sid, "failed")


def _serialize_caller_id(
    row: dict[str, Any], today: Optional[date] = None
) -> dict[str, Any]:
    phone_number = str(row.get("phone_number") or "")
    today = today or _today_madrid()
    return {
        "phoneNumber": row.get("phone_number"),
        "status": row.get("status"),
        "label": row.get("label"),
        "isDefault": bool(row.get("is_default")),
        "verifiedAt": row.get("verified_at"),
        "source": "user",
        "callBlocked": _mobile_call_blocked(phone_number, today),
        "notice": _caller_id_notice(phone_number, today),
    }


def list_caller_ids(
    supabase: Client, user_id: str, today: Optional[date] = None
) -> list[dict[str, Any]]:
    res = (
        supabase.table("user_caller_ids")
        .select("phone_number,status,label,is_default,verified_at")
        .eq("user_id", user_id)
        .order("created_at")
        .execute()
    )
    today = today or _today_madrid()
    return [_serialize_caller_id(row, today) for row in (res.data or [])]


def get_caller_id(
    supabase: Client, user_id: str, raw_number: str
) -> Optional[dict[str, Any]]:
    phone_number = normalize_e164(
        raw_number, default_country_code=settings.CALLING_DEFAULT_COUNTRY_CODE
    )
    rows = (
        supabase.table("user_caller_ids")
        .select("phone_number,status,label,is_default,verified_at")
        .eq("user_id", user_id)
        .eq("phone_number", phone_number)
        .limit(1)
        .execute()
        .data
    ) or []
    return _serialize_caller_id(rows[0]) if rows else None


def set_default_caller_id(supabase: Client, user_id: str, raw_number: str) -> bool:
    """Promote a verified number. Clears any other default for this user."""
    phone_number = normalize_e164(
        raw_number, default_country_code=settings.CALLING_DEFAULT_COUNTRY_CODE
    )
    existing = (
        supabase.table("user_caller_ids")
        .select("phone_number,status")
        .eq("user_id", user_id)
        .eq("phone_number", phone_number)
        .eq("status", "verified")
        .limit(1)
        .execute()
        .data
    ) or []
    if not existing:
        return False
    supabase.table("user_caller_ids").update({"is_default": False}).eq(
        "user_id", user_id
    ).eq("is_default", True).execute()
    res = (
        supabase.table("user_caller_ids")
        .update({"is_default": True})
        .eq("user_id", user_id)
        .eq("phone_number", phone_number)
        .eq("status", "verified")
        .execute()
    )
    return bool(res.data)


def update_caller_id_label(
    supabase: Client, user_id: str, raw_number: str, label: str
) -> bool:
    phone_number = normalize_e164(
        raw_number, default_country_code=settings.CALLING_DEFAULT_COUNTRY_CODE
    )
    res = (
        supabase.table("user_caller_ids")
        .update({"label": label})
        .eq("user_id", user_id)
        .eq("phone_number", phone_number)
        .execute()
    )
    return bool(res.data)


def _twilio_already_verified(exc: TwilioRestException) -> bool:
    if getattr(exc, "code", None) == 21450:
        return True
    return "already verified" in str(exc).lower()


def _claim_twilio_verified_number(
    supabase: Client,
    user_id: str,
    phone_number: str,
    label: Optional[str],
) -> dict[str, Any]:
    """Twilio still has the Outgoing Caller ID after we deleted our row."""
    found = twilio_rest().outgoing_caller_ids.list(
        phone_number=phone_number, limit=20
    )
    sid = found[0].sid if found else None
    now = datetime.now(timezone.utc).isoformat()
    upsert_row: dict[str, Any] = {
        "user_id": user_id,
        "phone_number": phone_number,
        "status": "verified",
        "verification_sid": sid,
        "verified_at": now,
    }
    if label is not None:
        upsert_row["label"] = label
    supabase.table("user_caller_ids").upsert(
        upsert_row,
        on_conflict="user_id,phone_number",
    ).execute()
    return {
        "phoneNumber": phone_number,
        "status": "verified",
        "validationSid": sid,
        "alreadyVerified": True,
    }


def _release_twilio_outgoing_caller_id(phone_number: str) -> None:
    if calling_provider() != "twilio":
        return
    found = twilio_rest().outgoing_caller_ids.list(
        phone_number=phone_number, limit=20
    )
    for row in found:
        row.delete()


def delete_caller_id(supabase: Client, user_id: str, raw_number: str) -> bool:
    phone_number = normalize_e164(
        raw_number, default_country_code=settings.CALLING_DEFAULT_COUNTRY_CODE
    )
    holders = (
        supabase.table("user_caller_ids")
        .select("user_id")
        .eq("phone_number", phone_number)
        .execute()
        .data
    ) or []
    if not any(row.get("user_id") == user_id for row in holders):
        return False
    if not any(row.get("user_id") != user_id for row in holders):
        _release_twilio_outgoing_caller_id(phone_number)
    res = (
        supabase.table("user_caller_ids")
        .delete()
        .eq("user_id", user_id)
        .eq("phone_number", phone_number)
        .execute()
    )
    return bool(res.data)


def resolve_caller_id(
    supabase: Client,
    user_id: str,
    requested: Optional[str],
    today: Optional[date] = None,
) -> str:
    """Authorize a caller ID for this user, or raise.

    The browser client sends a preference; this is the only place that decides.
    A client must never be able to present a number it does not own.
    A Spanish mobile past the block date raises `CallerIdRangeRestricted`
    (the row is kept); with no preference, the next verified number is used.
    """
    query = (
        supabase.table("user_caller_ids")
        .select("phone_number,status")
        .eq("user_id", user_id)
        .eq("status", "verified")
    )
    if requested:
        query = query.eq("phone_number", requested).limit(1)
    else:
        query = query.order("is_default", desc=True)

    rows = (query.execute().data) or []
    verified = [
        str(r["phone_number"]) for r in rows if r.get("status") == "verified"
    ]
    today = today or _today_madrid()
    allowed = [n for n in verified if not _mobile_call_blocked(n, today)]
    if allowed:
        return allowed[0]
    if verified:
        raise CallerIdRangeRestricted(ES_MOBILE_CALLER_ID_MESSAGE)
    raise CallerIdNotVerified(
        f"no verified caller ID for user {user_id} (requested={requested!r})"
    )
