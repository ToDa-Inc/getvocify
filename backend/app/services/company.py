"""Company workspace: membership, seats, invitations."""

from __future__ import annotations

import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status
from supabase import Client

from app.config import settings
from app.services.billing.entitlement import (
    ACCESS_MODES,
    access_mode_of,
    workspace_entitlements,
)
from app.services.feature_flags import is_enabled
from app.emails.templates import (
    build_invite_email_html,
    build_password_changed_email_html,
    build_password_reset_email_html,
    build_removed_email_html,
)
from app.integrations.resend_client import ResendClientError, get_resend_client, get_resend_from_email

logger = logging.getLogger(__name__)

INVITE_TOKEN_EXPIRY_DAYS = 7
PASSWORD_RESET_EXPIRY_HOURS = 1
MANAGE_ROLES = frozenset({"owner", "admin"})
INVITE_ROLES = frozenset({"admin", "member"})
REP_WORKSPACE_FLAG = "REP_WORKSPACE_ENABLED"


@dataclass
class Membership:
    id: str
    company_id: str
    user_id: str
    role: str
    status: str

    @property
    def is_active(self) -> bool:
        return self.status == "active"

    @property
    def can_manage_team(self) -> bool:
        return self.is_active and self.role in MANAGE_ROLES


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _missing_company_schema(exc: BaseException) -> bool:
    """True when company tables have not been migrated yet."""
    try:
        from postgrest.exceptions import APIError
    except ImportError:
        APIError = ()  # type: ignore[misc, assignment]

    if isinstance(exc, APIError):
        code = str(exc.code or "").upper()
        if code in ("PGRST205", "404"):
            return True
        msg = (exc.message or str(exc)).lower()
        if any(t in msg for t in ("company_members", "company_invitations", "companies")):
            if "could not find" in msg or "does not exist" in msg:
                return True

    msg = str(exc).lower()
    return (
        "pgrst205" in msg
        or 'relation "company_members" does not exist' in msg
        or ("404" in msg and "company_members" in msg)
    )


class CompanyService:
    def __init__(self, supabase: Client):
        self.supabase = supabase

    def get_membership(self, user_id: str) -> Optional[Membership]:
        try:
            result = (
                self.supabase.table("company_members")
                .select("id, company_id, user_id, role, status")
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
        except Exception as exc:
            if _missing_company_schema(exc):
                logger.warning(
                    "Company schema unavailable (run migration 028_companies.sql): %s",
                    exc,
                )
                return None
            raise
        rows = result.data or []
        if not rows:
            return None
        row = rows[0]
        return Membership(
            id=str(row["id"]),
            company_id=str(row["company_id"]),
            user_id=str(row["user_id"]),
            role=row["role"],
            status=row["status"],
        )

    def require_membership(self, user_id: str) -> Membership:
        membership = self.get_membership(user_id)
        if not membership or not membership.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No active company membership",
            )
        return membership

    def require_manage_role(self, user_id: str) -> Membership:
        membership = self.require_membership(user_id)
        if not membership.can_manage_team:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return membership

    def get_company(self, company_id: str) -> dict:
        result = (
            self.supabase.table("companies")
            .select("*")
            .eq("id", company_id)
            .single()
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=404, detail="Company not found")
        return result.data

    def count_active_members(self, company_id: str) -> int:
        result = (
            self.supabase.table("company_members")
            .select("id", count="exact")
            .eq("company_id", company_id)
            .eq("status", "active")
            .execute()
        )
        return int(result.count or 0)

    def count_pending_invites(self, company_id: str) -> int:
        now = _iso(_now())
        result = (
            self.supabase.table("company_invitations")
            .select("id", count="exact")
            .eq("company_id", company_id)
            .is_("accepted_at", "null")
            .is_("revoked_at", "null")
            .gt("expires_at", now)
            .execute()
        )
        return int(result.count or 0)

    def seats_used(self, company_id: str) -> int:
        return self.count_active_members(company_id) + self.count_pending_invites(company_id)

    def seat_usage(self, company_id: str) -> dict:
        company = self.get_company(company_id)
        active = self.count_active_members(company_id)
        pending = self.count_pending_invites(company_id)
        limit = int(company.get("seat_limit") or 1)
        return {
            "seat_limit": limit,
            "seats_active": active,
            "seats_pending": pending,
            "seats_used": active + pending,
            "seats_available": max(0, limit - active - pending),
            "access_mode": access_mode_of(company),
        }

    def ensure_seat_available(self, company_id: str) -> None:
        usage = self.seat_usage(company_id)
        if usage["seats_available"] <= 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No seats available. Remove a member or revoke a pending invite first.",
            )

    def create_company_for_owner(
        self,
        *,
        user_id: str,
        name: str,
        seat_limit: int = 1,
    ) -> str:
        company_row = {
            "name": name,
            "seat_limit": seat_limit,
            "created_by": user_id,
        }
        result = self.supabase.table("companies").insert(company_row).execute()
        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to create company")
        company_id = str(result.data[0]["id"])
        self.supabase.table("company_members").insert(
            {
                "company_id": company_id,
                "user_id": user_id,
                "role": "owner",
                "status": "active",
            }
        ).execute()
        self.supabase.table("user_profiles").update({"company_id": company_id}).eq(
            "id", user_id
        ).execute()
        return company_id

    def ensure_company_workspace(self, user_id: str, *, name: str) -> None:
        """Create a solo workspace when tables exist but the user has no membership."""
        try:
            if self.get_membership(user_id):
                return
            self.create_company_for_owner(user_id=user_id, name=name, seat_limit=1)
        except Exception as exc:
            if _missing_company_schema(exc):
                logger.warning(
                    "Skipping company workspace setup until migration 028 is applied: %s",
                    exc,
                )
                return
            raise

    def billing_for(self, company_id: str) -> dict:
        from app.services.billing.store import get_billing

        return get_billing(self.supabase, company_id) or {}

    def rep_workspace_enabled(self, company_id: str) -> bool:
        return is_enabled(self.supabase, company_id, REP_WORKSPACE_FLAG)

    def company_summary_for_user(self, user_id: str) -> Optional[dict]:
        membership = self.get_membership(user_id)
        if not membership or not membership.is_active:
            return None
        company = self.get_company(membership.company_id)
        usage = self.seat_usage(membership.company_id)
        billing = self.billing_for(membership.company_id)
        entitlements = workspace_entitlements(company, billing)
        return {
            "id": membership.company_id,
            "name": company.get("name"),
            "role": membership.role,
            "seat_limit": usage["seat_limit"],
            "seats_used": usage["seats_used"],
            "seats_pending": usage["seats_pending"],
            "seats_active": usage["seats_active"],
            "access_mode": entitlements["access_mode"],
            "billing_status": entitlements["billing_status"],
            "plan_type": entitlements["plan_type"],
            "paywalled": entitlements["paywalled"],
            "can_use_dialer": entitlements["can_use_dialer"],
            "rep_workspace_enabled": self.rep_workspace_enabled(membership.company_id),
        }

    def list_members(self, company_id: str) -> List[dict]:
        members_result = (
            self.supabase.table("company_members")
            .select("id, user_id, role, status, created_at")
            .eq("company_id", company_id)
            .order("created_at")
            .execute()
        )
        members = members_result.data or []
        user_ids = [m["user_id"] for m in members]
        profiles: Dict[str, dict] = {}
        if user_ids:
            prof_result = (
                self.supabase.table("user_profiles")
                .select("id, full_name")
                .in_("id", user_ids)
                .execute()
            )
            for p in prof_result.data or []:
                profiles[str(p["id"])] = p
        emails = self._auth_emails_by_ids(user_ids)
        out = []
        for m in members:
            uid = str(m["user_id"])
            out.append(
                {
                    "id": str(m["id"]),
                    "user_id": uid,
                    "email": emails.get(uid, ""),
                    "full_name": profiles.get(uid, {}).get("full_name"),
                    "role": m["role"],
                    "status": m["status"],
                    "created_at": m.get("created_at"),
                }
            )
        return out

    def list_pending_invites(self, company_id: str) -> List[dict]:
        now = _iso(_now())
        result = (
            self.supabase.table("company_invitations")
            .select("id, email, role, expires_at, created_at, invited_by")
            .eq("company_id", company_id)
            .is_("accepted_at", "null")
            .is_("revoked_at", "null")
            .gt("expires_at", now)
            .order("created_at", desc=True)
            .execute()
        )
        return [
            {
                "id": str(r["id"]),
                "email": str(r["email"]),
                "role": r["role"],
                "expires_at": r["expires_at"],
                "created_at": r.get("created_at"),
                "invited_by": r.get("invited_by"),
            }
            for r in (result.data or [])
        ]

    def _auth_emails_by_ids(self, user_ids: List[str]) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for uid in user_ids:
            try:
                user = self.supabase.auth.admin.get_user_by_id(uid)
                email = getattr(user, "email", None) or ""
                if hasattr(user, "user") and getattr(user.user, "email", None):
                    email = user.user.email
                if isinstance(user, dict):
                    email = user.get("email") or email
                out[uid] = email or ""
            except Exception as exc:
                logger.warning("Could not load auth email for %s: %s", uid, exc)
        return out

    def _email_exists_in_auth(self, email: str) -> Optional[str]:
        try:
            # list_users is paginated; for invites we only need existence check
            users = self.supabase.auth.admin.list_users()
            data = getattr(users, "users", None) or users
            if isinstance(data, list):
                for u in data:
                    uemail = getattr(u, "email", None) or (u.get("email") if isinstance(u, dict) else None)
                    if uemail and normalize_email(uemail) == normalize_email(email):
                        return str(getattr(u, "id", None) or (u.get("id") if isinstance(u, dict) else ""))
        except Exception as exc:
            logger.warning("Auth list_users failed during invite check: %s", exc)
        return None

    async def create_invite(
        self,
        *,
        company_id: str,
        email: str,
        role: str,
        invited_by: Optional[str] = None,
        send_email: bool = True,
    ) -> Tuple[dict, Optional[str], bool]:
        if role not in INVITE_ROLES:
            raise HTTPException(status_code=400, detail="Invalid invite role")
        email_norm = normalize_email(email)
        self.ensure_seat_available(company_id)

        # Already a member?
        existing_user_id = self._email_exists_in_auth(email_norm)
        if existing_user_id:
            existing_membership = self.get_membership(existing_user_id)
            if existing_membership and existing_membership.company_id == company_id:
                raise HTTPException(status_code=409, detail="User is already a member")
            if existing_membership:
                raise HTTPException(
                    status_code=409,
                    detail="User already belongs to another workspace",
                )

        # Revoke stale pending for same email then insert fresh
        self.supabase.table("company_invitations").update(
            {"revoked_at": _iso(_now())}
        ).eq("company_id", company_id).eq("email", email_norm).is_(
            "accepted_at", "null"
        ).is_("revoked_at", "null").execute()

        raw_token = secrets.token_urlsafe(32)
        expires = _now() + timedelta(days=INVITE_TOKEN_EXPIRY_DAYS)
        row = {
            "company_id": company_id,
            "email": email_norm,
            "role": role,
            "token_hash": hash_token(raw_token),
            "invited_by": invited_by,
            "expires_at": _iso(expires),
        }
        result = self.supabase.table("company_invitations").insert(row).execute()
        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to create invite")
        invite = result.data[0]
        company = self.get_company(company_id)
        invite_url = f"{settings.FRONTEND_URL.rstrip('/')}/invite/{raw_token}"
        email_sent = False
        if send_email:
            email_sent = await self._send_invite_email(
                to=email_norm,
                company_name=company.get("name") or "Vocify",
                invite_url=invite_url,
            )
        return invite, invite_url if not email_sent else None, email_sent

    async def resend_invite(self, invite_id: str, company_id: str) -> Tuple[dict, Optional[str], bool]:
        now = _iso(_now())
        result = (
            self.supabase.table("company_invitations")
            .select("*")
            .eq("id", invite_id)
            .eq("company_id", company_id)
            .is_("accepted_at", "null")
            .is_("revoked_at", "null")
            .gt("expires_at", now)
            .single()
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=404, detail="Invite not found or expired")
        raw_token = secrets.token_urlsafe(32)
        expires = _now() + timedelta(days=INVITE_TOKEN_EXPIRY_DAYS)
        updated = (
            self.supabase.table("company_invitations")
            .update({"token_hash": hash_token(raw_token), "expires_at": _iso(expires)})
            .eq("id", invite_id)
            .execute()
        )
        invite = (updated.data or [result.data])[0]
        company = self.get_company(company_id)
        invite_url = f"{settings.FRONTEND_URL.rstrip('/')}/invite/{raw_token}"
        email_sent = await self._send_invite_email(
            to=str(invite["email"]),
            company_name=company.get("name") or "Vocify",
            invite_url=invite_url,
        )
        return invite, invite_url if not email_sent else None, email_sent

    async def _send_invite_email(self, *, to: str, company_name: str, invite_url: str) -> bool:
        client = get_resend_client()
        if not client:
            logger.warning("Resend not configured; invite email skipped for %s", to)
            return False
        html = build_invite_email_html(
            company_name=company_name,
            invite_url=invite_url,
            expires_days=INVITE_TOKEN_EXPIRY_DAYS,
        )
        try:
            await client.send_email(
                to=to,
                subject=f"Invitation to join {company_name} on Vocify",
                html=html,
                from_email=get_resend_from_email("Vocify"),
            )
            return True
        except ResendClientError as exc:
            logger.warning("Invite email failed for %s: %s", to, exc)
            return False

    def revoke_invite(self, invite_id: str, company_id: str) -> None:
        now = _iso(_now())
        result = (
            self.supabase.table("company_invitations")
            .update({"revoked_at": now})
            .eq("id", invite_id)
            .eq("company_id", company_id)
            .is_("accepted_at", "null")
            .is_("revoked_at", "null")
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=404, detail="Invite not found")

    def get_invite_by_token(self, raw_token: str) -> dict:
        token_hash = hash_token(raw_token)
        now = _iso(_now())
        result = (
            self.supabase.table("company_invitations")
            .select("*, companies(name)")
            .eq("token_hash", token_hash)
            .is_("accepted_at", "null")
            .is_("revoked_at", "null")
            .gt("expires_at", now)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        if not rows:
            raise HTTPException(status_code=404, detail="Invite not found or expired")
        return rows[0]

    def accept_invite(
        self,
        *,
        raw_token: str,
        password: Optional[str],
        full_name: Optional[str],
        auth_client: Any,
    ) -> Tuple[str, str, str]:
        invite = self.get_invite_by_token(raw_token)
        company_id = str(invite["company_id"])
        email = str(invite["email"])
        role = invite["role"]

        existing_user_id = self._email_exists_in_auth(email)
        if existing_user_id:
            membership = self.get_membership(existing_user_id)
            if membership:
                if membership.company_id == company_id:
                    raise HTTPException(status_code=409, detail="Already a member")
                raise HTTPException(status_code=409, detail="User belongs to another workspace")
            user_id = existing_user_id
        else:
            if not password or len(password) < 8:
                raise HTTPException(status_code=400, detail="Password required (min 8 characters)")
            auth_response = auth_client.auth.sign_up({"email": email, "password": password})
            if not auth_response.user:
                raise HTTPException(status_code=400, detail="Failed to create account")
            user_id = str(auth_response.user.id)
            profile = {
                "id": user_id,
                "full_name": full_name,
                "company_id": company_id,
            }
            self.supabase.table("user_profiles").insert(profile).execute()

        self.supabase.table("company_members").insert(
            {
                "company_id": company_id,
                "user_id": user_id,
                "role": role,
                "status": "active",
            }
        ).execute()
        self.supabase.table("user_profiles").update({"company_id": company_id}).eq(
            "id", user_id
        ).execute()
        self.supabase.table("company_invitations").update(
            {"accepted_at": _iso(_now())}
        ).eq("id", invite["id"]).execute()
        return user_id, company_id, email

    def count_owners(self, company_id: str) -> int:
        result = (
            self.supabase.table("company_members")
            .select("id", count="exact")
            .eq("company_id", company_id)
            .eq("role", "owner")
            .eq("status", "active")
            .execute()
        )
        return int(result.count or 0)

    def update_member_role(
        self,
        *,
        company_id: str,
        member_id: str,
        role: str,
        actor: Membership,
    ) -> dict:
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="Only owners can change roles")
        if role not in ("owner", "admin", "member"):
            raise HTTPException(status_code=400, detail="Invalid role")
        target = self._get_member_row(company_id, member_id)
        if target["role"] == "owner" and role != "owner" and self.count_owners(company_id) <= 1:
            raise HTTPException(status_code=409, detail="Cannot demote the last owner")
        if target["role"] != "owner" and role == "owner":
            # Transfer ownership: demote current owner to admin
            self.supabase.table("company_members").update({"role": "admin"}).eq(
                "user_id", actor.user_id
            ).execute()
        result = (
            self.supabase.table("company_members")
            .update({"role": role, "updated_at": _iso(_now())})
            .eq("id", member_id)
            .eq("company_id", company_id)
            .execute()
        )
        return (result.data or [target])[0]

    def remove_member(
        self,
        *,
        company_id: str,
        member_id: str,
        actor: Membership,
    ) -> None:
        target = self._get_member_row(company_id, member_id)
        if str(target["user_id"]) == actor.user_id:
            raise HTTPException(status_code=400, detail="Cannot remove yourself")
        if target["role"] == "owner" and self.count_owners(company_id) <= 1:
            raise HTTPException(status_code=409, detail="Cannot remove the last owner")
        if actor.role == "admin" and target["role"] in ("owner", "admin"):
            raise HTTPException(status_code=403, detail="Admins cannot remove owners or other admins")

        self.supabase.table("company_members").delete().eq("id", member_id).execute()
        self.supabase.table("user_profiles").update({"company_id": None}).eq(
            "id", target["user_id"]
        ).execute()

    async def notify_removed(self, email: str, company_name: str) -> None:
        client = get_resend_client()
        if not client or not email:
            return
        try:
            await client.send_email(
                to=email,
                subject=f"Removed from {company_name} on Vocify",
                html=build_removed_email_html(company_name=company_name),
                from_email=get_resend_from_email("Vocify"),
            )
        except ResendClientError as exc:
            logger.warning("Removed notification failed: %s", exc)

    def _get_member_row(self, company_id: str, member_id: str) -> dict:
        result = (
            self.supabase.table("company_members")
            .select("*")
            .eq("id", member_id)
            .eq("company_id", company_id)
            .single()
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=404, detail="Member not found")
        return result.data

    def update_company_name(self, company_id: str, name: str) -> dict:
        name = name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Company name required")
        result = (
            self.supabase.table("companies")
            .update({"name": name, "updated_at": _iso(_now())})
            .eq("id", company_id)
            .execute()
        )
        return (result.data or [{}])[0]

    def update_seat_limit(self, company_id: str, seat_limit: int) -> dict:
        if seat_limit < 1:
            raise HTTPException(status_code=400, detail="seat_limit must be >= 1")
        usage = self.seat_usage(company_id)
        if seat_limit < usage["seats_used"]:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot set seat_limit below current occupancy ({usage['seats_used']})",
            )
        result = (
            self.supabase.table("companies")
            .update({"seat_limit": seat_limit, "updated_at": _iso(_now())})
            .eq("id", company_id)
            .execute()
        )
        return (result.data or [{}])[0]

    def update_access_mode(self, company_id: str, access_mode: str) -> dict:
        if access_mode not in ACCESS_MODES:
            raise HTTPException(status_code=400, detail="access_mode must be open, paywalled, or unlocked")
        result = (
            self.supabase.table("companies")
            .update({"access_mode": access_mode, "updated_at": _iso(_now())})
            .eq("id", company_id)
            .execute()
        )
        return (result.data or [{}])[0]

    def admin_set_member_role(self, company_id: str, member_id: str, role: str) -> dict:
        if role not in ("owner", "admin", "member"):
            raise HTTPException(status_code=400, detail="Invalid role")
        target = self._get_member_row(company_id, member_id)
        if target["role"] == "owner" and role != "owner" and self.count_owners(company_id) <= 1:
            raise HTTPException(status_code=409, detail="Cannot demote the last owner")
        if role == "owner" and target["role"] != "owner":
            self.supabase.table("company_members").update(
                {"role": "admin", "updated_at": _iso(_now())}
            ).eq("company_id", company_id).eq("role", "owner").execute()
        result = (
            self.supabase.table("company_members")
            .update({"role": role, "updated_at": _iso(_now())})
            .eq("id", member_id)
            .eq("company_id", company_id)
            .execute()
        )
        return (result.data or [target])[0]

    def admin_remove_member(self, company_id: str, member_id: str) -> dict:
        target = self._get_member_row(company_id, member_id)
        if target["role"] == "owner" and self.count_owners(company_id) <= 1:
            raise HTTPException(status_code=409, detail="Cannot remove the last owner")
        self.supabase.table("company_members").delete().eq("id", member_id).execute()
        self.supabase.table("user_profiles").update({"company_id": None}).eq(
            "id", target["user_id"]
        ).execute()
        return target

    def transfer_member(
        self,
        *,
        user_id: str,
        to_company_id: str,
        role: str = "member",
    ) -> None:
        membership = self.get_membership(user_id)
        if not membership:
            raise HTTPException(status_code=404, detail="User has no membership")
        if membership.company_id == to_company_id:
            return
        if membership.role == "owner" and self.count_owners(membership.company_id) <= 1:
            raise HTTPException(status_code=409, detail="Cannot transfer the last owner")
        self.ensure_seat_available(to_company_id)
        self.supabase.table("company_members").delete().eq("user_id", user_id).execute()
        self.supabase.table("company_members").insert(
            {
                "company_id": to_company_id,
                "user_id": user_id,
                "role": role if role != "owner" else "member",
                "status": "active",
            }
        ).execute()
        self.supabase.table("user_profiles").update({"company_id": to_company_id}).eq(
            "id", user_id
        ).execute()

    async def create_password_reset(self, email: str) -> None:
        user_id = self._email_exists_in_auth(email)
        if not user_id:
            return
        now = _iso(_now())
        self.supabase.table("password_reset_tokens").update({"used_at": now}).eq(
            "user_id", user_id
        ).is_("used_at", "null").execute()
        raw_token = secrets.token_urlsafe(32)
        expires = _now() + timedelta(hours=PASSWORD_RESET_EXPIRY_HOURS)
        self.supabase.table("password_reset_tokens").insert(
            {
                "user_id": user_id,
                "token_hash": hash_token(raw_token),
                "expires_at": _iso(expires),
            }
        ).execute()
        reset_url = f"{settings.FRONTEND_URL.rstrip('/')}/reset-password/{raw_token}"
        client = get_resend_client()
        if not client:
            logger.warning("Resend not configured; password reset email skipped")
            return
        html = build_password_reset_email_html(
            reset_url=reset_url,
            expires_hours=PASSWORD_RESET_EXPIRY_HOURS,
        )
        try:
            await client.send_email(
                to=normalize_email(email),
                subject="Reset your Vocify password",
                html=html,
                from_email=get_resend_from_email("Vocify"),
            )
        except ResendClientError as exc:
            logger.warning("Password reset email failed: %s", exc)

    def email_for_user(self, user_id: str) -> Optional[str]:
        email = (self._auth_emails_by_ids([user_id]).get(user_id) or "").strip()
        return email or None

    def consume_password_reset(self, raw_token: str, new_password: str) -> Optional[str]:
        token_hash = hash_token(raw_token)
        now = _iso(_now())
        result = (
            self.supabase.table("password_reset_tokens")
            .select("*")
            .eq("token_hash", token_hash)
            .is_("used_at", "null")
            .gt("expires_at", now)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        if not rows:
            raise HTTPException(status_code=400, detail="Invalid or expired reset link")
        row = rows[0]
        user_id = str(row["user_id"])
        self.supabase.auth.admin.update_user_by_id(user_id, {"password": new_password})
        self.supabase.table("password_reset_tokens").update(
            {"used_at": now}
        ).eq("id", row["id"]).execute()
        return self.email_for_user(user_id)

    async def notify_password_changed(self, email: str) -> None:
        client = get_resend_client()
        if not client or not email:
            return
        try:
            await client.send_email(
                to=email,
                subject="Your Vocify password was changed",
                html=build_password_changed_email_html(),
                from_email=get_resend_from_email("Vocify"),
            )
        except ResendClientError as exc:
            logger.warning("Password changed email failed: %s", exc)


def get_company_id_for_user(supabase: Client, user_id: str) -> Optional[str]:
    svc = CompanyService(supabase)
    membership = svc.get_membership(user_id)
    return membership.company_id if membership and membership.is_active else None
