"""Fields AI can fill, per sales role and per person - the Head of Sales' editor.

GET    /api/v1/crm/field-permissions?provider=hubspot
PUT    /api/v1/crm/field-permissions/roles/{sales_role}
DELETE /api/v1/crm/field-permissions/roles/{sales_role}
PUT    /api/v1/crm/field-permissions/members/{user_id}
DELETE /api/v1/crm/field-permissions/members/{user_id}

Owner/admin only. Pipeline, stages, Skip Approve and create contacts/companies stay in the
company's CRM configuration (POST /crm/hubspot/configure) and apply to everyone.
"""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from supabase import Client

from app.deps import get_supabase, get_user_id
from app.services.company import CompanyService, Membership
from app.services.company_scope import require_crm_connection
from app.services.crm_field_permissions import (
    ROLE_KEYS,
    SCOPE_MEMBER,
    SCOPE_ROLE,
    delete_permission,
    list_permissions,
    save_permission,
)

router = APIRouter(prefix="/api/v1/crm/field-permissions", tags=["crm"])

Provider = Literal["hubspot", "salesforce", "pipedrive"]


class FieldListsBody(BaseModel):
    """None = inherit from the level below (role for a person, company for a role)."""

    allowed_deal_fields: Optional[list[str]] = None
    allowed_contact_fields: Optional[list[str]] = None
    allowed_company_fields: Optional[list[str]] = None
    allowed_line_item_fields: Optional[list[str]] = None


def _manager_and_connection(supabase: Client, user_id: str, provider: str) -> tuple[Membership, dict]:
    membership = CompanyService(supabase).require_manage_role(user_id)
    connection = require_crm_connection(supabase, user_id, provider)
    return membership, connection


def _require_role(sales_role: str) -> str:
    if sales_role not in ROLE_KEYS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid sales role")
    return sales_role


def _require_member(svc: CompanyService, company_id: str, member_user_id: str) -> None:
    members = svc.list_members(company_id)
    if not any(m["user_id"] == str(member_user_id) and m["status"] == "active" for m in members):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")


@router.get("")
async def get_field_permissions(
    provider: Provider = Query("hubspot"),
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    membership, connection = _manager_and_connection(supabase, user_id, provider)
    svc = CompanyService(supabase)
    sales_roles_on = svc.sales_roles_enabled(membership.company_id)
    stored = list_permissions(supabase, connection_id=str(connection["id"]))
    members = [
        {
            "user_id": m["user_id"],
            "email": m.get("email") or "",
            "full_name": m.get("full_name"),
            "role": m["role"],
            "sales_role": m.get("sales_role") if sales_roles_on else None,
            "fields": stored["members"].get(m["user_id"]),
        }
        for m in svc.list_members(membership.company_id, include_sales_fields=sales_roles_on)
        if m["status"] == "active"
    ]
    return {
        "sales_roles_enabled": sales_roles_on,
        "roles": stored["roles"],
        "members": members,
    }


@router.put("/roles/{sales_role}")
async def put_role_fields(
    sales_role: str,
    body: FieldListsBody,
    provider: Provider = Query("hubspot"),
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    membership, connection = _manager_and_connection(supabase, user_id, provider)
    fields = save_permission(
        supabase,
        company_id=membership.company_id,
        connection_id=str(connection["id"]),
        scope=SCOPE_ROLE,
        scope_key=_require_role(sales_role),
        fields=body.model_dump(),
        updated_by=user_id,
    )
    return {"sales_role": sales_role, "fields": fields}


@router.delete("/roles/{sales_role}")
async def delete_role_fields(
    sales_role: str,
    provider: Provider = Query("hubspot"),
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    _membership, connection = _manager_and_connection(supabase, user_id, provider)
    delete_permission(
        supabase,
        connection_id=str(connection["id"]),
        scope=SCOPE_ROLE,
        scope_key=_require_role(sales_role),
    )
    return {"success": True}


@router.put("/members/{member_user_id}")
async def put_member_fields(
    member_user_id: str,
    body: FieldListsBody,
    provider: Provider = Query("hubspot"),
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    membership, connection = _manager_and_connection(supabase, user_id, provider)
    _require_member(CompanyService(supabase), membership.company_id, member_user_id)
    fields = save_permission(
        supabase,
        company_id=membership.company_id,
        connection_id=str(connection["id"]),
        scope=SCOPE_MEMBER,
        scope_key=str(member_user_id),
        fields=body.model_dump(),
        updated_by=user_id,
    )
    return {"user_id": str(member_user_id), "fields": fields}


@router.delete("/members/{member_user_id}")
async def delete_member_fields(
    member_user_id: str,
    provider: Provider = Query("hubspot"),
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    _membership, connection = _manager_and_connection(supabase, user_id, provider)
    delete_permission(
        supabase,
        connection_id=str(connection["id"]),
        scope=SCOPE_MEMBER,
        scope_key=str(member_user_id),
    )
    return {"success": True}
