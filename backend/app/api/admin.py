"""
Internal admin API — master-key gated account console.
"""

import logging
import re
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
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
from app.services.company import CompanyService
from app.services.recovery import RecoveryService
from pydantic import BaseModel, EmailStr, Field

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


def _unwrap_auth_user(response: Any) -> Any:
    user = getattr(response, "user", None)
    return user if user is not None else response


def _auth_user_row(user: Any) -> dict:
    user = _unwrap_auth_user(user)
    last_sign_in = getattr(user, "last_sign_in_at", None)
    if last_sign_in is not None and hasattr(last_sign_in, "isoformat"):
        last_sign_in = last_sign_in.isoformat()
    return {
        "id": str(getattr(user, "id", "") or ""),
        "email": getattr(user, "email", None) or "",
        "last_sign_in_at": last_sign_in,
    }


def _auth_users_by_ids(supabase: Client, ids: List[str]) -> List[dict]:
    if not ids:
        return []
    rows: List[dict] = []
    for uid in ids:
        try:
            user = supabase.auth.admin.get_user_by_id(uid)
            if user:
                rows.append(_auth_user_row(user))
        except Exception as exc:
            logger.warning("admin get_user_by_id failed for %s: %s", uid, exc)
    return rows


def _auth_user_by_id(supabase: Client, user_id: str) -> Optional[dict]:
    rows = _auth_users_by_ids(supabase, [user_id])
    return rows[0] if rows else None


def _auth_user_ids_matching_email(supabase: Client, query: str) -> set[str]:
    needle = query.strip().lower()
    if not needle:
        return set()
    matched: set[str] = set()
    page = 1
    per_page = 200
    while True:
        try:
            users = supabase.auth.admin.list_users(page=page, per_page=per_page)
        except Exception as exc:
            logger.warning("admin list_users failed on page %s: %s", page, exc)
            break
        if not users:
            break
        for user in users:
            row = _auth_user_row(user)
            email = (row.get("email") or "").lower()
            if needle in email:
                matched.add(row["id"])
        if len(users) < per_page:
            break
        page += 1
    return matched


def _profile_ids_for_search(supabase: Client, search: str) -> Optional[List[str]]:
    q = search.strip()
    if not q:
        return None

    ids: set[str] = set()
    if "@" in q:
        ids.update(_auth_user_ids_matching_email(supabase, q))

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
        user=_user_response(uid, email, profile, supabase),
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


class AdminCreateCompanyRequest(BaseModel):
    name: str
    seat_limit: int = Field(default=1, ge=1)
    owner_email: Optional[EmailStr] = None


class AdminUpdateCompanyRequest(BaseModel):
    name: Optional[str] = None
    seat_limit: Optional[int] = Field(default=None, ge=1)


class AdminTransferMemberRequest(BaseModel):
    to_company_id: UUID
    role: str = "member"


@router.get("/companies")
async def list_companies(
    skip: int = 0,
    limit: int = 20,
    search: Optional[str] = None,
    supabase: Client = Depends(get_supabase),
    _: str = Depends(require_master_key),
):
    limit = max(1, min(limit, 100))
    skip = max(0, skip)
    query = supabase.table("companies").select("id,name,seat_limit,created_at", count="exact")
    if search and search.strip():
        query = query.ilike("name", f"%{search.strip()}%")
    count_result = query.execute()
    total = count_result.count or 0
    list_result = (
        supabase.table("companies")
        .select("id,name,seat_limit,created_at")
        .order("created_at", desc=True)
        .range(skip, skip + limit - 1)
    )
    if search and search.strip():
        list_result = list_result.ilike("name", f"%{search.strip()}%")
    companies = (list_result.execute().data) or []
    svc = CompanyService(supabase)
    items = []
    for c in companies:
        cid = str(c["id"])
        usage = svc.seat_usage(cid)
        members = svc.count_active_members(cid)
        conn = (
            supabase.table("crm_connections")
            .select("provider,status")
            .eq("company_id", cid)
            .execute()
        )
        items.append(
            {
                "id": cid,
                "name": c.get("name"),
                "seat_limit": usage["seat_limit"],
                "seats_used": usage["seats_used"],
                "member_count": members,
                "crm": conn.data or [],
                "created_at": c.get("created_at"),
            }
        )
    return {"companies": items, "total": total, "skip": skip, "limit": limit}


@router.get("/companies/{company_id}")
async def get_company_admin(
    company_id: UUID,
    supabase: Client = Depends(get_supabase),
    _: str = Depends(require_master_key),
):
    cid = str(company_id)
    svc = CompanyService(supabase)
    company = svc.get_company(cid)
    usage = svc.seat_usage(cid)
    members = svc.list_members(cid)
    invites = svc.list_pending_invites(cid)
    connections = (
        supabase.table("crm_connections").select("*").eq("company_id", cid).execute().data or []
    )
    return {
        "company": {
            "id": cid,
            "name": company.get("name"),
            "seat_limit": usage["seat_limit"],
            "seats_used": usage["seats_used"],
            "seats_pending": usage["seats_pending"],
            "glossary_count": len(company.get("glossary") or []),
            "product_context_preview": (company.get("product_context") or "")[:200],
            "auto_create_contact_company": company.get("auto_create_contact_company"),
            "created_at": company.get("created_at"),
        },
        "members": members,
        "pending_invites": invites,
        "crm_connections": connections,
    }


@router.patch("/companies/{company_id}")
async def update_company_admin(
    company_id: UUID,
    body: AdminUpdateCompanyRequest,
    supabase: Client = Depends(get_supabase),
    _: str = Depends(require_master_key),
):
    cid = str(company_id)
    svc = CompanyService(supabase)
    if body.name is not None:
        svc.update_company_name(cid, body.name)
    if body.seat_limit is not None:
        svc.update_seat_limit(cid, body.seat_limit)
    _write_audit(supabase, "update_company", metadata={"company_id": cid, **body.model_dump(exclude_none=True)})
    return {"success": True}


@router.post("/companies")
async def create_company_admin(
    body: AdminCreateCompanyRequest,
    supabase: Client = Depends(get_supabase),
    _: str = Depends(require_master_key),
):
    svc = CompanyService(supabase)
    # Create placeholder owner if email provided and user exists
    owner_id = None
    if body.owner_email:
        owner_id = svc._email_exists_in_auth(body.owner_email)
    row = {
        "name": body.name.strip(),
        "seat_limit": body.seat_limit,
        "created_by": owner_id,
    }
    result = supabase.table("companies").insert(row).execute()
    company_id = str(result.data[0]["id"])
    if owner_id:
        supabase.table("company_members").insert(
            {"company_id": company_id, "user_id": owner_id, "role": "owner", "status": "active"}
        ).execute()
        supabase.table("user_profiles").update({"company_id": company_id}).eq("id", owner_id).execute()
    _write_audit(supabase, "create_company", metadata={"company_id": company_id, "name": body.name})
    return {"success": True, "company_id": company_id}


class AdminAddMemberRequest(BaseModel):
    user_id: UUID
    role: str = "member"


@router.post("/companies/{company_id}/members")
async def add_member_to_company_admin(
    company_id: UUID,
    body: AdminAddMemberRequest,
    supabase: Client = Depends(get_supabase),
    _: str = Depends(require_master_key),
):
    cid = str(company_id)
    svc = CompanyService(supabase)
    svc.ensure_seat_available(cid)
    uid = str(body.user_id)
    existing = svc.get_membership(uid)
    if existing:
        raise HTTPException(status_code=409, detail="User already belongs to a workspace")
    svc.supabase.table("company_members").insert(
        {
            "company_id": cid,
            "user_id": uid,
            "role": body.role if body.role != "owner" else "member",
            "status": "active",
        }
    ).execute()
    svc.supabase.table("user_profiles").update({"company_id": cid}).eq("id", uid).execute()
    _write_audit(
        supabase,
        "add_company_member",
        target_user_id=uid,
        metadata={"company_id": cid, "role": body.role},
    )
    return {"success": True}


@router.post("/members/{user_id}/transfer")
async def transfer_member_admin(
    user_id: UUID,
    body: AdminTransferMemberRequest,
    supabase: Client = Depends(get_supabase),
    _: str = Depends(require_master_key),
):
    svc = CompanyService(supabase)
    svc.transfer_member(
        user_id=str(user_id),
        to_company_id=str(body.to_company_id),
        role=body.role,
    )
    _write_audit(
        supabase,
        "transfer_member",
        target_user_id=str(user_id),
        metadata={"to_company_id": str(body.to_company_id), "role": body.role},
    )
    return {"success": True}
