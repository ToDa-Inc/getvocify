"""Company workspace API."""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from supabase import Client

from app.deps import get_supabase, get_supabase_auth, get_user_id
from app.services.company import CompanyService, INVITE_ROLES

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/company", tags=["company"])


class CompanyResponse(BaseModel):
    id: str
    name: str
    seat_limit: int
    seats_used: int
    seats_pending: int
    seats_active: int
    seats_available: int
    role: str


class UpdateCompanyRequest(BaseModel):
    name: Optional[str] = None


class InviteRequest(BaseModel):
    email: EmailStr
    role: str = Field(default="member")
    send_email: bool = True


class InviteResponse(BaseModel):
    id: str
    email: str
    role: str
    expires_at: str
    email_sent: bool
    invite_url: Optional[str] = None


class MemberResponse(BaseModel):
    id: str
    user_id: str
    email: str
    full_name: Optional[str] = None
    role: str
    status: str
    created_at: Optional[str] = None


class PendingInviteResponse(BaseModel):
    id: str
    email: str
    role: str
    expires_at: str
    created_at: Optional[str] = None


class MembersListResponse(BaseModel):
    members: List[MemberResponse]
    pending_invites: List[PendingInviteResponse]


class UpdateMemberRoleRequest(BaseModel):
    role: str


class AcceptInviteRequest(BaseModel):
    token: str
    password: Optional[str] = Field(default=None, min_length=8)
    full_name: Optional[str] = None


class AcceptInviteResponse(BaseModel):
    success: bool
    message: str


@router.get("", response_model=CompanyResponse)
async def get_company(
    user_id: str = Depends(get_user_id),
    supabase: Client = Depends(get_supabase),
):
    svc = CompanyService(supabase)
    membership = svc.require_membership(user_id)
    company = svc.get_company(membership.company_id)
    usage = svc.seat_usage(membership.company_id)
    return CompanyResponse(
        id=membership.company_id,
        name=company.get("name") or "",
        seat_limit=usage["seat_limit"],
        seats_used=usage["seats_used"],
        seats_pending=usage["seats_pending"],
        seats_active=usage["seats_active"],
        seats_available=usage["seats_available"],
        role=membership.role,
    )


@router.patch("", response_model=CompanyResponse)
async def update_company(
    body: UpdateCompanyRequest,
    user_id: str = Depends(get_user_id),
    supabase: Client = Depends(get_supabase),
):
    svc = CompanyService(supabase)
    membership = svc.require_manage_role(user_id)
    if body.name:
        svc.update_company_name(membership.company_id, body.name)
    return await get_company(user_id=user_id, supabase=supabase)


@router.get("/members", response_model=MembersListResponse)
async def list_members(
    user_id: str = Depends(get_user_id),
    supabase: Client = Depends(get_supabase),
):
    svc = CompanyService(supabase)
    membership = svc.require_membership(user_id)
    members = svc.list_members(membership.company_id)
    invites = svc.list_pending_invites(membership.company_id)
    can_see_invites = membership.can_manage_team
    return MembersListResponse(
        members=[MemberResponse(**m) for m in members],
        pending_invites=[PendingInviteResponse(**i) for i in invites] if can_see_invites else [],
    )


@router.post("/invites", response_model=InviteResponse)
async def create_invite(
    body: InviteRequest,
    user_id: str = Depends(get_user_id),
    supabase: Client = Depends(get_supabase),
):
    if body.role not in INVITE_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")
    svc = CompanyService(supabase)
    membership = svc.require_manage_role(user_id)
    invite, invite_url, email_sent = await svc.create_invite(
        company_id=membership.company_id,
        email=body.email,
        role=body.role,
        invited_by=user_id,
        send_email=body.send_email,
    )
    return InviteResponse(
        id=str(invite["id"]),
        email=str(invite["email"]),
        role=invite["role"],
        expires_at=invite["expires_at"],
        email_sent=email_sent,
        invite_url=invite_url,
    )


@router.post("/invites/{invite_id}/resend", response_model=InviteResponse)
async def resend_invite(
    invite_id: str,
    user_id: str = Depends(get_user_id),
    supabase: Client = Depends(get_supabase),
):
    svc = CompanyService(supabase)
    membership = svc.require_manage_role(user_id)
    invite, invite_url, email_sent = await svc.resend_invite(invite_id, membership.company_id)
    return InviteResponse(
        id=str(invite["id"]),
        email=str(invite["email"]),
        role=invite["role"],
        expires_at=invite["expires_at"],
        email_sent=email_sent,
        invite_url=invite_url,
    )


@router.delete("/invites/{invite_id}")
async def revoke_invite(
    invite_id: str,
    user_id: str = Depends(get_user_id),
    supabase: Client = Depends(get_supabase),
):
    svc = CompanyService(supabase)
    membership = svc.require_manage_role(user_id)
    svc.revoke_invite(invite_id, membership.company_id)
    return {"success": True}


@router.patch("/members/{member_id}")
async def update_member_role(
    member_id: str,
    body: UpdateMemberRoleRequest,
    user_id: str = Depends(get_user_id),
    supabase: Client = Depends(get_supabase),
):
    svc = CompanyService(supabase)
    membership = svc.require_membership(user_id)
    updated = svc.update_member_role(
        company_id=membership.company_id,
        member_id=member_id,
        role=body.role,
        actor=membership,
    )
    return {"success": True, "role": updated.get("role")}


@router.delete("/members/{member_id}")
async def remove_member(
    member_id: str,
    user_id: str = Depends(get_user_id),
    supabase: Client = Depends(get_supabase),
):
    svc = CompanyService(supabase)
    membership = svc.require_manage_role(user_id)
    target = svc._get_member_row(membership.company_id, member_id)
    emails = svc._auth_emails_by_ids([str(target["user_id"])])
    company = svc.get_company(membership.company_id)
    svc.remove_member(
        company_id=membership.company_id,
        member_id=member_id,
        actor=membership,
    )
    await svc.notify_removed(
        emails.get(str(target["user_id"]), ""),
        company.get("name") or "Vocify",
    )
    return {"success": True}


@router.get("/invites/preview")
async def preview_invite(token: str, supabase: Client = Depends(get_supabase)):
    svc = CompanyService(supabase)
    invite = svc.get_invite_by_token(token)
    company = invite.get("companies") or {}
    email = str(invite["email"])
    existing_user_id = svc._email_exists_in_auth(email)
    return {
        "email": email,
        "role": invite["role"],
        "company_name": company.get("name") if isinstance(company, dict) else None,
        "expires_at": invite["expires_at"],
        "requires_password": not existing_user_id,
    }


@router.post("/invites/accept", response_model=AcceptInviteResponse)
async def accept_invite(
    body: AcceptInviteRequest,
    supabase: Client = Depends(get_supabase),
    auth_client: Client = Depends(get_supabase_auth),
):
    svc = CompanyService(supabase)
    svc.accept_invite(
        raw_token=body.token,
        password=body.password,
        full_name=body.full_name,
        auth_client=auth_client,
    )
    return AcceptInviteResponse(success=True, message="Invitation accepted. You can now log in.")
