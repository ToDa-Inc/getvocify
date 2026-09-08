from __future__ import annotations

import logging
from typing import Any

from supabase import Client

from app.services.telephony.telnyx_client import telnyx_rest

logger = logging.getLogger(__name__)

TOKEN_TTL_SECONDS_TELNYX = 24 * 3600


def _is_unique_violation(exc: Exception) -> bool:
    text = str(exc).lower()
    return "duplicate key" in text or "23505" in text


def _lookup_credential(supabase: Client, user_id: str) -> dict[str, str] | None:
    rows = (
        supabase.table("user_telephony_credentials")
        .select("credential_id,sip_username")
        .eq("user_id", user_id)
        .eq("provider", "telnyx")
        .limit(1)
        .execute()
        .data
    ) or []
    if not rows:
        return None
    row = rows[0]
    return {
        "credentialId": row["credential_id"],
        "sipUsername": row["sip_username"],
    }


def ensure_user_credential(supabase: Client, user_id: str) -> dict[str, str]:
    existing = _lookup_credential(supabase, user_id)
    if existing:
        return existing

    created = telnyx_rest().create_telephony_credential(name=f"vocify-{user_id}")
    row = {
        "user_id": user_id,
        "provider": "telnyx",
        "credential_id": created["credential_id"],
        "sip_username": created["sip_username"],
    }
    try:
        supabase.table("user_telephony_credentials").insert(row).execute()
    except Exception as exc:
        if not _is_unique_violation(exc):
            raise
        winner = _lookup_credential(supabase, user_id)
        if not winner:
            raise
        try:
            telnyx_rest().delete_telephony_credential(created["credential_id"])
        except Exception:
            logger.exception(
                "Failed to revoke orphan Telnyx credential %s",
                created["credential_id"],
            )
        return winner
    return {
        "credentialId": created["credential_id"],
        "sipUsername": created["sip_username"],
    }


def mint_telnyx_voice_token(supabase: Client, user_id: str) -> dict[str, Any]:
    credential = ensure_user_credential(supabase, user_id)
    token = telnyx_rest().mint_credential_token(credential["credentialId"])
    return {
        "token": token,
        "identity": str(user_id),
        "expiresIn": TOKEN_TTL_SECONDS_TELNYX,
        "provider": "telnyx",
    }
