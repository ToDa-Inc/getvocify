"""
Internal admin API — master-key gated account console.
"""

import logging
import re
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from supabase import Client

from app.api.auth import AuthResponse, _user_response
from app.config import settings
from app.deps import get_supabase, require_master_key
from app.services.admin_accounts import (
    assemble_account_detail,
    assemble_account_list_items,
    compute_usage_from_memos,
)
from app.services.admin_session import mint_session_for_email
from app.services.recovery import RecoveryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _write_audit(
    supabase: Client,
    action: str,
    target_user_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    try:
        supabase.table("admin_audit_log").insert(
            {
                "action": action,
                "target_user_id": target_user_id,
                "metadata": metadata or {},
            }
        ).execute()
    except Exception as exc:
        logger.warning("admin audit insert failed (%s): %s", action, exc)


def _auth_users_by_ids(supabase: Client, ids: List[str]) -> List[dict]:
    if not ids:
        return []
    result = (
        supabase.postgrest.schema("auth")
        .from_("users")
        .select("id,email,last_sign_in_at")
        .in_("id", ids)
        .execute()
    )
    return result.data or []


def _auth_user_by_id(supabase: Client, user_id: str) -> Optional[dict]:
    rows = _auth_users_by_ids(supabase, [user_id])
    return rows[0] if rows else None


def _profile_ids_for_search(supabase: Client, search: str) -> Optional[List[str]]:
    q = search.strip()
    if not q:
        return None

    ids: set[str] = set()
    if "@" in q:
        auth_result = (
            supabase.postgrest.schema("auth")
            .from_("users")
            .select("id")
            .ilike("email", f"%{q}%")
            .limit(200)
            .execute()
        )
        ids.update(str(r["id"]) for r in (auth_result.data or []) if r.get("id"))

    profile_query = supabase.table("user_profiles").select("id")
    if _UUID_RE.match(q):
        profile_query = profile_query.or_(f"full_name.ilike.%{q}%,company_name.ilike.%{q}%,id.eq.{q}")
    else:
        profile_query = profile_query.or_(f"full_name.ilike.%{q}%,company_name.ilike.%{q}%")
    profile_result = profile_query.limit(200).execute()
    ids.update(str(r["id"]) for r in (profile_result.data or []) if r.get("id"))
    return list(ids)


@router.get("/accounts")
async def list_accounts(
    skip: int = 0,
    limit: int = 20,
    search: Optional[str] = None,
    supabase: Client = Depends(get_supabase),
    _: str = Depends(require_master_key),
):
    limit = max(1, min(limit, 100))
    skip = max(0, skip)

    search_ids = _profile_ids_for_search(supabase, search) if search and search.strip() else None
    if search_ids is not None and not search_ids:
        return {"accounts": [], "total": 0, "skip": skip, "limit": limit}

    count_query = supabase.table("user_profiles").select("id", count="exact")
    list_query = (
        supabase.table("user_profiles")
        .select("id,full_name,company_name,phone,created_at")
        .order("created_at", desc=True)
    )
    if search_ids is not None:
        count_query = count_query.in_("id", search_ids)
        list_query = list_query.in_("id", search_ids)

    count_result = count_query.execute()
    total = count_result.count or 0

    profiles_result = list_query.range(skip, skip + limit - 1).execute()
    profiles = profiles_result.data or []
    profile_ids = [str(p["id"]) for p in profiles if p.get("id")]

    auth_users = _auth_users_by_ids(supabase, profile_ids)
    connections: List[dict] = []
    memos: List[dict] = []
    if profile_ids:
        conn_result = (
            supabase.table("crm_connections")
            .select("user_id,provider,status,token_expires_at")
            .in_("user_id", profile_ids)
            .execute()
        )
        connections = conn_result.data or []
        memo_result = (
            supabase.table("memos")
            .select("user_id,status,created_at")
            .in_("user_id", profile_ids)
            .execute()
        )
        memos = memo_result.data or []

    accounts = assemble_account_list_items(profiles, auth_users, connections, memos)
    return {"accounts": accounts, "total": total, "skip": skip, "limit": limit}


@router.get("/accounts/{user_id}")
async def get_account(
    user_id: UUID,
    supabase: Client = Depends(get_supabase),
    _: str = Depends(require_master_key),
):
    uid = str(user_id)
    profile_result = supabase.table("user_profiles").select("*").eq("id", uid).limit(1).execute()
    if not profile_result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    profile = profile_result.data[0]

    auth_user = _auth_user_by_id(supabase, uid) or {}

    conn_result = supabase.table("crm_connections").select("*").eq("user_id", uid).execute()
    connections = conn_result.data or []
    connection_ids = [str(c["id"]) for c in connections if c.get("id")]

    configurations: List[dict] = []
    if connection_ids:
        cfg_result = (
            supabase.table("crm_configurations")
            .select("*")
            .in_("connection_id", connection_ids)
            .execute()
        )
        configurations = cfg_result.data or []

    recent_result = (
        supabase.table("memos")
        .select("id,status,source,created_at,extraction,error_message")
        .eq("user_id", uid)
        .order("created_at", desc=True)
        .limit(20)
        .execute()
    )
    recent_memos = recent_result.data or []

    usage_rows_result = (
        supabase.table("memos")
        .select("id,status,created_at,audio_duration,extraction")
        .eq("user_id", uid)
        .order("created_at", desc=True)
        .limit(2000)
        .execute()
    )
    usage = compute_usage_from_memos(usage_rows_result.data or [])

    return assemble_account_detail(profile, auth_user, connections, configurations, recent_memos, usage)


@router.post("/accounts/{user_id}/impersonate", response_model=AuthResponse)
async def impersonate_account(
    user_id: UUID,
    supabase: Client = Depends(get_supabase),
    _: str = Depends(require_master_key),
):
    uid = str(user_id)
    auth_user = _auth_user_by_id(supabase, uid)
    if not auth_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    email = (auth_user.get("email") or "").strip()
    minted = mint_session_for_email(email)

    profile_result = supabase.table("user_profiles").select("*").eq("id", uid).limit(1).execute()
    profile = profile_result.data[0] if profile_result.data else {}

    _write_audit(supabase, "impersonate", target_user_id=uid, metadata={"email": email})

    return AuthResponse(
        user=_user_response(uid, email, profile),
        access_token=minted.access_token,
        refresh_token=minted.refresh_token,
    )


@router.get("/stuck-memos")
async def list_stuck_memos(
    supabase: Client = Depends(get_supabase),
    _: str = Depends(require_master_key),
):
    recovery = RecoveryService(supabase)
    memos = await recovery.find_stuck_memos()
    return {
        "memos": [
            {
                "id": m.get("id"),
                "user_id": m.get("user_id"),
                "status": m.get("status"),
                "processing_started_at": m.get("processing_started_at"),
                "error_message": m.get("error_message"),
            }
            for m in memos
        ]
    }


@router.post("/recover-stuck-memos")
async def recover_stuck_memos_admin(
    supabase: Client = Depends(get_supabase),
    _: str = Depends(require_master_key),
):
    recovery = RecoveryService(supabase)
    result = await recovery.recover_all_stuck_memos()
    _write_audit(supabase, "recover_stuck_memos", metadata=result)
    return {"status": "completed", **result}


@router.get("/runtime")
async def admin_runtime(_: str = Depends(require_master_key)):
    return {
        "stt_provider": settings.STT_PROVIDER,
        "llm_provider": settings.LLM_PROVIDER,
        "extraction_model": settings.EXTRACTION_MODEL,
        "copilot_model": settings.COPILOT_MODEL,
        "environment": settings.ENVIRONMENT,
    }
