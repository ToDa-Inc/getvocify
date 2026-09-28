"""Company workspace API."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from supabase import Client

from app.deps import get_supabase, get_supabase_auth, get_user_id
from app.services.billing.entitlement import workspace_entitlements
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
    access_mode: str = "open"
    billing_status: str = "none"
    plan_type: Optional[str] = None
    billing_interval: Optional[str] = None
    paywalled: bool = False
    can_use_dialer: bool = True
    rep_workspace_enabled: bool = False
    brief_v2_enabled: bool = False
    sales_strategy: Optional[str] = None
    # T5: days after an unanswered call before Hoy suggests calling back. Only sent while
    # HOY_LEAD_TIERS_ENABLED is on for the company (None otherwise).
    callback_after_days: Optional[int] = None
    needs_onboarding: bool = False


class UpdateCompanyRequest(BaseModel):
    name: Optional[str] = None
    sales_strategy: Optional[str] = None
    callback_after_days: Optional[int] = Field(default=None, ge=1, le=30)


class InviteRequest(BaseModel):
    email: EmailStr
    role: str = Field(default="member")
    send_email: bool = True
    sales_role: Optional[str] = None


class InviteResponse(BaseModel):
    id: str
    email: str
    role: str
    expires_at: str
    email_sent: bool
    invite_url: Optional[str] = None
    sales_role: Optional[str] = None
    crm_owner_match: Optional[bool] = None


class MemberResponse(BaseModel):
    id: str
    user_id: str
    email: str
    full_name: Optional[str] = None
    role: str
    status: str
    created_at: Optional[str] = None
    sales_role: Optional[str] = None
    handoff_ae_user_id: Optional[str] = None
    visibility: Optional[str] = None


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
    role: Optional[str] = None
    sales_role: Optional[str] = None
    handoff_ae_user_id: Optional[str] = None
    visibility: Optional[str] = None


class AcceptInviteRequest(BaseModel):
    token: str
    password: Optional[str] = Field(default=None, min_length=8)
    full_name: Optional[str] = None


class AcceptInviteResponse(BaseModel):
    success: bool
    message: str
    user: Optional[dict] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None


@router.get("", response_model=CompanyResponse)
async def get_company(
    user_id: str = Depends(get_user_id),
    supabase: Client = Depends(get_supabase),
):
    svc = CompanyService(supabase)
    membership = svc.require_membership(user_id)
    company = svc.get_company(membership.company_id)
    usage = svc.seat_usage(membership.company_id)
    billing = svc.billing_for(membership.company_id)
    entitlements = workspace_entitlements(company, billing)
    return CompanyResponse(
        id=membership.company_id,
        name=company.get("name") or "",
        seat_limit=usage["seat_limit"],
        seats_used=usage["seats_used"],
        seats_pending=usage["seats_pending"],
        seats_active=usage["seats_active"],
        seats_available=usage["seats_available"],
        role=membership.role,
        access_mode=entitlements["access_mode"],
        billing_status=entitlements["billing_status"],
        plan_type=entitlements["plan_type"],
        billing_interval=billing.get("billing_interval"),
        paywalled=entitlements["paywalled"],
        can_use_dialer=entitlements["can_use_dialer"],
        rep_workspace_enabled=svc.rep_workspace_enabled(membership.company_id),
        brief_v2_enabled=svc.brief_v2_enabled(membership.company_id),
        sales_strategy=company.get("sales_strategy") if svc.sales_strategy_enabled(membership.company_id) else None,
        callback_after_days=(
            svc.callback_after_days(membership.company_id) if svc.lead_tiers_enabled(membership.company_id) else None
        ),
        needs_onboarding=svc.needs_onboarding(membership, company),
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
    if body.sales_strategy is not None and svc.sales_strategy_enabled(membership.company_id):
        svc.update_sales_strategy(membership.company_id, body.sales_strategy)
    if body.callback_after_days is not None and svc.lead_tiers_enabled(membership.company_id):
        svc.update_callback_after_days(membership.company_id, body.callback_after_days)
    return await get_company(user_id=user_id, supabase=supabase)


class OnboardingStateResponse(BaseModel):
    needed: bool
    next_step: Optional[str] = None
    state: Dict[str, bool] = Field(default_factory=dict)


@router.get("/onboarding", response_model=OnboardingStateResponse)
async def get_onboarding_state(
    user_id: str = Depends(get_user_id),
    supabase: Client = Depends(get_supabase),
):
    """T9: what step the Head of Sales onboarding wizard should show next. Owner/admin only,
    same as the wizard itself."""
    from app.services.onboarding import next_onboarding_step

    svc = CompanyService(supabase)
    membership = svc.require_manage_role(user_id)
    state = svc.onboarding_state(membership.company_id)
    return OnboardingStateResponse(
        needed=svc.needs_onboarding(membership),
        next_step=next_onboarding_step(state),
        state=state,
    )


@router.post("/onboarding/complete", response_model=CompanyResponse)
async def complete_onboarding(
    user_id: str = Depends(get_user_id),
    supabase: Client = Depends(get_supabase),
):
    """T9: finish (or skip through) the wizard. Owner/admin only."""
    svc = CompanyService(supabase)
    membership = svc.require_manage_role(user_id)
    svc.complete_onboarding(membership.company_id)
    return await get_company(user_id=user_id, supabase=supabase)


@router.get("/members", response_model=MembersListResponse)
async def list_members(
    user_id: str = Depends(get_user_id),
    supabase: Client = Depends(get_supabase),
):
    svc = CompanyService(supabase)
    membership = svc.require_membership(user_id)
    sales_roles_on = svc.sales_roles_enabled(membership.company_id)
    members = svc.list_members(membership.company_id, include_sales_fields=sales_roles_on)
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
    sales_role = body.sales_role if svc.sales_roles_enabled(membership.company_id) else None
    invite, invite_url, email_sent, crm_owner_match = await svc.create_invite(
        company_id=membership.company_id,
        email=body.email,
        role=body.role,
        invited_by=user_id,
        send_email=body.send_email,
        sales_role=sales_role,
    )
    return InviteResponse(
        id=str(invite["id"]),
        email=str(invite["email"]),
        role=invite["role"],
        expires_at=invite["expires_at"],
        email_sent=email_sent,
        invite_url=invite_url,
        sales_role=invite.get("sales_role"),
        crm_owner_match=crm_owner_match,
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
    updated: dict = {}

    # Sales fields are validated (and applied) before any role change, so a bad
    # sales_role/handoff/visibility never leaves the role half-updated.
    sales_fields_sent = {"sales_role", "handoff_ae_user_id", "visibility"} & body.model_fields_set
    if sales_fields_sent and svc.sales_roles_enabled(membership.company_id):
        kwargs: Dict[str, Any] = {}
        if "sales_role" in sales_fields_sent:
            kwargs["sales_role"] = body.sales_role
        if "handoff_ae_user_id" in sales_fields_sent:
            kwargs["handoff_ae_user_id"] = body.handoff_ae_user_id
        if "visibility" in sales_fields_sent:
            kwargs["visibility"] = body.visibility
        updated = svc.update_member_profile(
            company_id=membership.company_id,
            actor=membership,
            member_id=member_id,
            **kwargs,
        )

    if body.role is not None:
        updated = svc.update_member_role(
            company_id=membership.company_id,
            member_id=member_id,
            role=body.role,
            actor=membership,
        )

    return {
        "success": True,
        "role": updated.get("role"),
        "sales_role": updated.get("sales_role"),
        "handoff_ae_user_id": (str(updated["handoff_ae_user_id"]) if updated.get("handoff_ae_user_id") else None),
        "visibility": updated.get("visibility"),
    }


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
        "sales_role": invite.get("sales_role"),
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
    from app.api.auth import _user_response
    from app.services.admin_session import mint_session_for_email

    svc = CompanyService(supabase)
    user_id, _company_id, email = svc.accept_invite(
        raw_token=body.token,
        password=body.password,
        full_name=body.full_name,
        auth_client=auth_client,
    )
    minted = mint_session_for_email(email)
    profile_result = (
        supabase.table("user_profiles").select("*").eq("id", user_id).limit(1).execute()
    )
    profile = (profile_result.data or [{}])[0]
    user = _user_response(user_id, email, profile, supabase)
    return AcceptInviteResponse(
        success=True,
        message="Invitation accepted",
        user=user.model_dump(),
        access_token=minted.access_token,
        refresh_token=minted.refresh_token,
    )
