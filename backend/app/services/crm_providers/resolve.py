"""
Resolve which crm_connections row is used for memo sync, preview, match, and default config.

Rules:
- If user_profiles.primary_crm_connection_id is set and that connection exists and is connected → use it.
- Else if exactly one row in crm_connections for user with status=connected → use it.
- Else if zero connected → return None.
- Else (multiple connected, no primary) → raise AmbiguousPrimaryCRMError.
"""

from __future__ import annotations

from typing import Any, Optional

from supabase import Client

from app.services.crm_providers.errors import AmbiguousPrimaryCRMError


def resolve_sync_connection(supabase: Client, user_id: str) -> Optional[dict[str, Any]]:
    """
    Returns the connection dict or None if no connected CRM.
    Raises AmbiguousPrimaryCRMError if 2+ connected and no primary set.
    """
    connected = (
        supabase.table("crm_connections")
        .select("*")
        .eq("user_id", user_id)
        .eq("status", "connected")
        .execute()
    )
    rows = connected.data or []

    if not rows:
        return None

    if len(rows) == 1:
        return rows[0]

    profile = (
        supabase.table("user_profiles")
        .select("primary_crm_connection_id")
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )
    primary_id = None
    if profile and profile.data:
        primary_id = profile.data.get("primary_crm_connection_id")

    if primary_id:
        for r in rows:
            if str(r.get("id")) == str(primary_id):
                return r
        # Stale primary pointing to deleted/disconnected — treat as ambiguous
        raise AmbiguousPrimaryCRMError()

    raise AmbiguousPrimaryCRMError()


def count_connected_crms(supabase: Client, user_id: str) -> int:
    r = (
        supabase.table("crm_connections")
        .select("id")
        .eq("user_id", user_id)
        .eq("status", "connected")
        .execute()
    )
    return len(r.data or [])
