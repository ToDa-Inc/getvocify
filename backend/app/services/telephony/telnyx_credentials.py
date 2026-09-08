from __future__ import annotations

from typing import Any

from supabase import Client

from app.services.telephony.telnyx_client import telnyx_rest

TOKEN_TTL_SECONDS_TELNYX = 24 * 3600


def ensure_user_credential(supabase: Client, user_id: str) -> dict[str, str]:
    rows = (
        supabase.table("user_telephony_credentials")
        .select("credential_id,sip_username")
        .eq("user_id", user_id)
        .eq("provider", "telnyx")
        .limit(1)
        .execute()
        .data
    ) or []
    if rows:
        row = rows[0]
        return {
            "credentialId": row["credential_id"],
            "sipUsername": row["sip_username"],
        }

    created = telnyx_rest().create_telephony_credential(name=f"vocify-{user_id}")
    supabase.table("user_telephony_credentials").insert(
        {
            "user_id": user_id,
            "provider": "telnyx",
            "credential_id": created["credential_id"],
            "sip_username": created["sip_username"],
        }
    ).execute()
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
