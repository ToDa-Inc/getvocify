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

from app.services.company import get_company_id_for_user
from app.services.crm_providers.errors import AmbiguousPrimaryCRMError


def resolve_sync_connection_for_company(
    supabase: Client, company_id: str
) -> Optional[dict[str, Any]]:
    """
    Returns the connection dict or None if no connected CRM for a company.
    Raises AmbiguousPrimaryCRMError if 2+ connected and no primary set.
    """
    connected = (
        supabase.table("crm_connections")
        .select("*")
        .eq("company_id", company_id)
        .eq("status", "connected")
        .execute()
    )
    rows = connected.data or []

    if not rows:
        return None

    if len(rows) == 1:
        return rows[0]

    company = (
        supabase.table("companies")
        .select("primary_crm_connection_id")
        .eq("id", company_id)
        .maybe_single()
        .execute()
    )
    primary_id = None
    if company and company.data:
        primary_id = company.data.get("primary_crm_connection_id")

    if primary_id:
        for r in rows:
            if str(r.get("id")) == str(primary_id):
                return r
        raise AmbiguousPrimaryCRMError()

    raise AmbiguousPrimaryCRMError()


def resolve_sync_connection(supabase: Client, user_id: str) -> Optional[dict[str, Any]]:
    """Resolve CRM connection for the user's company workspace."""
    company_id = get_company_id_for_user(supabase, user_id)
    if not company_id:
        return None
    return resolve_sync_connection_for_company(supabase, company_id)


def count_connected_crms(supabase: Client, user_id: str) -> int:
    company_id = get_company_id_for_user(supabase, user_id)
    if not company_id:
        return 0
    r = (
        supabase.table("crm_connections")
        .select("id")
        .eq("company_id", company_id)
        .eq("status", "connected")
        .execute()
    )
    return len(r.data or [])
