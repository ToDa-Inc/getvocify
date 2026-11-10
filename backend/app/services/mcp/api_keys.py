"""One personal API key per user, kept as three columns on user_profiles. Only its hash is stored.

A key is read-only (`vk_…`) or can also edit the company's setup (`vkw_…`: playbooks, company knowledge, offer).
The access is part of the key itself, fixed when it is made, the way restricted keys work elsewhere: a key made
before edits existed is a `vk_` key and stays read-only. Changing the access means making a new key.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone
from typing import Any, Optional

KEY_PREFIX = "vk_"
WRITE_KEY_PREFIX = "vkw_"
_PREFIX_SHOWN = 10  # the kind plus 6-7 characters: enough to tell two keys apart, useless to guess one
_COLUMNS = "api_key_prefix,api_key_created_at"


def is_api_key(token: str) -> bool:
    return token.startswith((KEY_PREFIX, WRITE_KEY_PREFIX))


def can_write(key_or_prefix: Optional[str]) -> bool:
    """Whether a key (or its stored prefix) is one that may edit the company's setup."""
    return bool(key_or_prefix) and str(key_or_prefix).startswith(WRITE_KEY_PREFIX)


def hash_key(key: str) -> str:
    """SHA-256 is enough: the key is 32 random bytes, not a password someone chose."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _status(row: Optional[dict]) -> dict:
    prefix = (row or {}).get("api_key_prefix")
    return {
        "has_key": bool(prefix),
        "prefix": prefix or None,
        "created_at": (row or {}).get("api_key_created_at") if prefix else None,
        "can_write": can_write(prefix),
    }


def key_status(supabase: Any, user_id: str) -> dict:
    rows = (
        supabase.table("user_profiles").select(_COLUMNS).eq("id", user_id).limit(1).execute().data or []
    )
    return _status(rows[0] if rows else None)


def generate_key(supabase: Any, user_id: str, *, write: bool = False) -> dict:
    """A new key replaces the old one, which stops working at once. The key is returned only here. `write`: the
    key may also edit the company's setup (the caller checks the user may grant that)."""
    key = (WRITE_KEY_PREFIX if write else KEY_PREFIX) + secrets.token_urlsafe(32)
    values = {
        "api_key_hash": hash_key(key),
        "api_key_prefix": key[:_PREFIX_SHOWN],
        "api_key_created_at": datetime.now(timezone.utc).isoformat(),
    }
    updated = supabase.table("user_profiles").update(values).eq("id", user_id).execute().data or []
    if not updated:
        supabase.table("user_profiles").insert({"id": user_id, **values}).execute()
    return {"key": key, **_status(values)}


def revoke_key(supabase: Any, user_id: str) -> None:
    (
        supabase.table("user_profiles")
        .update({"api_key_hash": None, "api_key_prefix": None, "api_key_created_at": None})
        .eq("id", user_id)
        .execute()
    )


def user_for_key(supabase: Any, key: str) -> Optional[str]:
    """The user a key belongs to, or None. Read on every request, so a revoked key fails on its next call."""
    if not is_api_key(key):
        return None
    rows = (
        supabase.table("user_profiles").select("id").eq("api_key_hash", hash_key(key)).limit(1).execute().data
        or []
    )
    return str(rows[0]["id"]) if rows and rows[0].get("id") else None


def keys_of(supabase: Any, user_ids: list[str]) -> dict[str, dict]:
    """{user_id: key status} for the members who have a key."""
    if not user_ids:
        return {}
    rows = (
        supabase.table("user_profiles")
        .select("id," + _COLUMNS)
        .in_("id", user_ids)
        .execute()
        .data
        or []
    )
    return {str(row["id"]): _status(row) for row in rows if row.get("api_key_prefix")}
