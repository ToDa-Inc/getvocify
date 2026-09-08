"""Helpers to resolve company scope from a user id."""

from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, status
from supabase import Client

from app.services.company import CompanyService, get_company_id_for_user


def require_company_id(supabase: Client, user_id: str) -> str:
    company_id = get_company_id_for_user(supabase, user_id)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active company membership",
        )
    return company_id


def require_crm_write_access(supabase: Client, user_id: str) -> str:
    """Return company_id if user may connect/disconnect CRM or edit shared settings."""
    svc = CompanyService(supabase)
    membership = svc.require_manage_role(user_id)
    return membership.company_id


def get_crm_connection(
    supabase: Client,
    user_id: str,
    provider: str,
) -> Optional[dict]:
    company_id = get_company_id_for_user(supabase, user_id)
    if not company_id:
        return None
    result = (
        supabase.table("crm_connections")
        .select("*")
        .eq("company_id", company_id)
        .eq("provider", provider)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    return rows[0] if rows else None


def require_crm_connection(
    supabase: Client,
    user_id: str,
    provider: str,
    *,
    detail: str = "CRM connection not found",
) -> dict:
    row = get_crm_connection(supabase, user_id, provider)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    return row
