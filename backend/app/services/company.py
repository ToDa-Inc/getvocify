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
from app.services.ttl_cache import TtlCache
from app.services.hoy.materialize import DEFAULT_CALLBACK_AFTER_DAYS
from app.emails.templates import (
    build_invite_email_html,
    build_password_changed_email_html,
    build_password_reset_email_html,
    build_removed_email_html,
)
from app.integrations.resend_client import ResendClientError, get_resend_client, get_resend_from_email

logger = logging.getLogger(__name__)

# Auth emails by user id; shown as names/authors, so a few minutes of staleness is harmless.
_AUTH_EMAILS: TtlCache[str] = TtlCache(300.0)

INVITE_TOKEN_EXPIRY_DAYS = 7
PASSWORD_RESET_EXPIRY_HOURS = 1
MANAGE_ROLES = frozenset({"owner", "admin"})
INVITE_ROLES = frozenset({"admin", "member"})
REP_WORKSPACE_FLAG = "REP_WORKSPACE_ENABLED"
BRIEF_V2_FLAG = "BRIEF_V2_ENABLED"
SALES_ROLES_FLAG = "SALES_ROLES_ENABLED"
FOLLOWUP_BY_FLOW_FLAG = "FOLLOWUP_BY_FLOW_ENABLED"
ONBOARDING_WIZARD_FLAG = "ONBOARDING_WIZARD_ENABLED"
SALES_ROLES = frozenset({"sdr", "ae", "general"})
VISIBILITIES = frozenset({"own", "team"})


@dataclass
class Membership:
    id: str
    company_id: str
    user_id: str
    role: str
    status: str
    sales_role: Optional[str] = None
    handoff_ae_user_id: Optional[str] = None
    visibility: str = "own"

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


def _missing_sales_strategy_column(exc: BaseException) -> bool:
    """True when migration 058_sales_strategy.sql (companies.sales_strategy) has not run
    yet: an undefined-column error naming that column."""
    try:
        from postgrest.exceptions import APIError
    except ImportError:
        APIError = ()  # type: ignore[misc, assignment]

    if isinstance(exc, APIError):
        code = str(exc.code or "").upper()
        msg = (exc.message or str(exc)).lower()
        if (code == "42703" or "does not exist" in msg) and "sales_strategy" in msg:
            return True

    msg = str(exc).lower()
    return "42703" in msg and "sales_strategy" in msg


def _missing_onboarding_column(exc: BaseException) -> bool:
    """True when migration 059_company_onboarding.sql (companies.onboarding_completed_at)
    has not run yet: an undefined-column error naming that column."""
    try:
        from postgrest.exceptions import APIError
    except ImportError:
        APIError = ()  # type: ignore[misc, assignment]

    if isinstance(exc, APIError):
        code = str(exc.code or "").upper()
        msg = (exc.message or str(exc)).lower()
        if (code == "42703" or "does not exist" in msg) and "onboarding_completed_at" in msg:
            return True

    msg = str(exc).lower()
    return "42703" in msg and "onboarding_completed_at" in msg


_SALES_COLUMN_NAMES = ("sales_role", "handoff_ae_user_id", "visibility")


def _missing_sales_columns(exc: BaseException) -> bool:
    """True when migration 054_sales_roles.sql (sales_role/handoff_ae_user_id/visibility)
    has not run yet: an undefined-column error naming one of those columns."""
    try:
        from postgrest.exceptions import APIError
    except ImportError:
        APIError = ()  # type: ignore[misc, assignment]

    if isinstance(exc, APIError):
        code = str(exc.code or "").upper()
        msg = (exc.message or str(exc)).lower()
        if (code == "42703" or "does not exist" in msg) and any(n in msg for n in _SALES_COLUMN_NAMES):
            return True

    msg = str(exc).lower()
    return "42703" in msg and any(n in msg for n in _SALES_COLUMN_NAMES)


def sales_role_for_user(supabase: Client, user_id: str, *, company_id: Optional[str] = None) -> Optional[str]:
    """Best-effort sales_role lookup for capture routing (D5). Tolerant of the sales_role
    column not existing yet (delegates to get_membership) and never raises. When the caller
    already knows the company (T12 reports), `company_id` scopes the result to it: a
    membership row for a different company is treated as "no role", not that company's."""
    try:
        membership = CompanyService(supabase).get_membership(str(user_id))
    except Exception as exc:
        logger.warning("sales_role lookup failed for %s: %s", user_id, exc)
        return None
    if not membership:
        return None
    if company_id is not None and str(membership.company_id) != str(company_id):
        return None
    return membership.sales_role


class CompanyService:
    def __init__(self, supabase: Client):
        self.supabase = supabase

    def get_membership(self, user_id: str) -> Optional[Membership]:
        try:
            result = (
                self.supabase.table("company_members")
                .select("id, company_id, user_id, role, status, sales_role, handoff_ae_user_id, visibility")
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
        except Exception as exc:
            # Checked before _missing_company_schema: an undefined sales_role/etc. column
            # error also mentions "company_members" and "does not exist", so the more
            # specific check must run first or it never fires.
            if _missing_sales_columns(exc):
                logger.warning(
                    "sales_role/handoff_ae_user_id/visibility unavailable (run migration "
                    "054_sales_roles.sql): %s",
                    exc,
                )
                result = (
                    self.supabase.table("company_members")
                    .select("id, company_id, user_id, role, status")
                    .eq("user_id", user_id)
                    .limit(1)
                    .execute()
                )
            elif _missing_company_schema(exc):
                logger.warning(
                    "Company schema unavailable (run migration 028_companies.sql): %s",
                    exc,
                )
                return None
            else:
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
            sales_role=row.get("sales_role"),
            handoff_ae_user_id=(str(row["handoff_ae_user_id"]) if row.get("handoff_ae_user_id") else None),
            visibility=row.get("visibility") or "own",
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

    def callback_after_days(self, company_id: str) -> int:
        """T5 (companies.callback_after_days, migration 057): how many silent days after a
        no_response/voicemail call attempt Hoy surfaces callback_no_answer. Read with
        select("*") like get_company, so a company row without the column yet (migration
        not applied) never raises - it just falls back to the same default of 2."""
        try:
            company = self.get_company(company_id)
        except Exception:
            return DEFAULT_CALLBACK_AFTER_DAYS
        value = company.get("callback_after_days")
        return int(value) if isinstance(value, int) and value > 0 else DEFAULT_CALLBACK_AFTER_DAYS

    def followup_cadence(self, company_id: str) -> dict[str, int]:
        """Lista 4 T2 (companies.followup_cadence, migration 062): the Head of Sales' own
        follow-up waits per stopper, validated (hoy/cadence.parse_overrides). Read with
        select("*") like callback_after_days, so before the migration - or on any failed
        read - it is {} and E8's defaults apply."""
        from app.services.hoy.cadence import parse_overrides

        try:
            company = self.get_company(company_id)
        except Exception:
            return {}
        return parse_overrides(company.get("followup_cadence"))

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

    def brief_v2_enabled(self, company_id: str) -> bool:
        return is_enabled(self.supabase, company_id, BRIEF_V2_FLAG)

    def sales_roles_enabled(self, company_id: str) -> bool:
        return is_enabled(self.supabase, company_id, SALES_ROLES_FLAG)

    def sales_strategy_enabled(self, company_id: str) -> bool:
        """D10 rides on the follow-up-by-flow flag: that is the only consumer so far."""
        return is_enabled(self.supabase, company_id, FOLLOWUP_BY_FLOW_FLAG)

    def lead_tiers_enabled(self, company_id: str) -> bool:
        """T5: callback_after_days only matters (and is only editable) with lead tiers on."""
        return is_enabled(self.supabase, company_id, "HOY_LEAD_TIERS_ENABLED")

    def sdr_sections_enabled(self, company_id: str) -> bool:
        """Lista 4: the follow-up cadence only matters (and is only editable) with the SDR's
        Tareas / Seguimiento / Nuevos on - it is what brings a contact back to Seguimiento."""
        return is_enabled(self.supabase, company_id, "HOY_SDR_SECTIONS_ENABLED")

    def onboarding_wizard_enabled(self, company_id: str) -> bool:
        return is_enabled(self.supabase, company_id, ONBOARDING_WIZARD_FLAG)

    def needs_onboarding(self, membership: "Membership", company: Optional[dict] = None) -> bool:
        """T9: only a Head of Sales (owner/admin) ever gets the wizard, and only while the
        flag is on. Pass `company` when the caller already has the row (company_summary_for_user,
        GET /company) to skip a second read.

        `onboarding_completed_at` comes back through get_company's `select("*")`, so a company
        on a database before migration 059 simply has no such key in the row - that reads as
        "not asking for onboarding" (pre-migration behaviour unchanged), not as "incomplete".
        Once the column exists, an explicit None means incomplete."""
        if not membership.can_manage_team:
            return False
        if not self.onboarding_wizard_enabled(membership.company_id):
            return False
        row = company if company is not None else self.get_company(membership.company_id)
        if "onboarding_completed_at" not in row:
            return False
        return row.get("onboarding_completed_at") is None

    def onboarding_state(self, company_id: str) -> dict:
        """Best-effort read of which onboarding steps already look done, for the wizard to
        skip ahead. `playbooks` has no cheap signal (its store lives in memory, see
        api/playbooks.py) so it always starts pending; the wizard's own skip covers it."""
        from app.services.onboarding import STEPS

        company = self.get_company(company_id)
        members = self.list_members(company_id, include_sales_fields=True)
        sdrs = [m for m in members if m.get("sales_role") == "sdr"]
        state = {
            "crm": bool(company.get("primary_crm_connection_id")),
            "team": self.count_active_members(company_id) > 1 or bool(self.list_pending_invites(company_id)),
            "handoff": not sdrs or any(m.get("handoff_ae_user_id") for m in sdrs),
            "playbooks": False,
            "strategy": bool((company.get("sales_strategy") or "").strip()),
        }
        return {step: state[step] for step in STEPS}

    def complete_onboarding(self, company_id: str) -> dict:
        """Owner/admin only (require_manage_role at the API layer). Tolerant of migration
        059_company_onboarding.sql not having run yet, same pattern as update_sales_strategy."""
        try:
            result = (
                self.supabase.table("companies")
                .update({"onboarding_completed_at": _iso(_now())})
                .eq("id", company_id)
                .execute()
            )
            return (result.data or [{}])[0]
        except Exception as exc:
            if _missing_onboarding_column(exc):
                logger.warning(
                    "onboarding_completed_at unavailable (run migration 059_company_onboarding.sql): %s", exc,
                )
                return self.get_company(company_id)
            raise

    def company_summary_for_user(self, user_id: str) -> Optional[dict]:
        from app.services.feature_flags import CLIENT_FLAGS, enabled_features

        membership = self.get_membership(user_id)
        if not membership or not membership.is_active:
            return None
        company = self.get_company(membership.company_id)
        usage = self.seat_usage(membership.company_id)
        billing = self.billing_for(membership.company_id)
        entitlements = workspace_entitlements(company, billing)
        sales_roles_on = self.sales_roles_enabled(membership.company_id)
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
            "brief_v2_enabled": self.brief_v2_enabled(membership.company_id),
            "sales_role": membership.sales_role if sales_roles_on else None,
            # T13: the current user's own visibility, so the frontend can tell a
            # visibility=team member it may load /dashboard/insights, same rule as
            # activity_scope.can_view_company_activity.
            "visibility": membership.visibility if sales_roles_on else None,
            "features": enabled_features(self.supabase, membership.company_id, CLIENT_FLAGS),
            "needs_onboarding": self.needs_onboarding(membership, company),
        }

    def list_members(self, company_id: str, *, include_sales_fields: bool = False) -> List[dict]:
        select_cols = "id, user_id, role, status, created_at"
        if include_sales_fields:
            select_cols += ", sales_role, handoff_ae_user_id, visibility"
        members_result = (
            self.supabase.table("company_members")
            .select(select_cols)
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
            row = {
                "id": str(m["id"]),
                "user_id": uid,
                "email": emails.get(uid, ""),
                "full_name": profiles.get(uid, {}).get("full_name"),
                "role": m["role"],
                "status": m["status"],
                "created_at": m.get("created_at"),
            }
            if include_sales_fields:
                handoff = m.get("handoff_ae_user_id")
                row["sales_role"] = m.get("sales_role")
                row["handoff_ae_user_id"] = str(handoff) if handoff else None
                row["visibility"] = m.get("visibility") or "own"
            out.append(row)
        return out

    def list_pending_invites(self, company_id: str) -> List[dict]:
        now = _iso(_now())
        base_cols = "id, email, role, expires_at, created_at, invited_by"

        def _read(columns: str):
            return (
                self.supabase.table("company_invitations")
                .select(columns)
                .eq("company_id", company_id)
                .is_("accepted_at", "null")
                .is_("revoked_at", "null")
                .gt("expires_at", now)
                .order("created_at", desc=True)
                .execute()
            )

        try:
            result = _read(f"{base_cols}, sales_role")
        except Exception as exc:
            # Column only exists after migration 054; keep listing invites without it.
            if not _missing_sales_columns(exc):
                raise
            result = _read(base_cols)
        return [
            {
                "id": str(r["id"]),
                "email": str(r["email"]),
                "role": r["role"],
                "expires_at": r["expires_at"],
                "created_at": r.get("created_at"),
                "invited_by": r.get("invited_by"),
                "sales_role": r.get("sales_role"),
            }
            for r in (result.data or [])
        ]

    def _auth_emails_by_ids(self, user_ids: List[str]) -> Dict[str, str]:
        """Emails by user id. Each is one blocking call to the auth service, and every page of a
        memo lists the same few members, so a found email is kept for a few minutes."""
        out: Dict[str, str] = {}
        for uid in user_ids:
            cached = _AUTH_EMAILS.get(uid)
            if cached is not None:
                out[uid] = cached
                continue
            try:
                user = self.supabase.auth.admin.get_user_by_id(uid)
                email = getattr(user, "email", None) or ""
                if hasattr(user, "user") and getattr(user.user, "email", None):
                    email = user.user.email
                if isinstance(user, dict):
                    email = user.get("email") or email
                out[uid] = email or ""
                if email:
                    _AUTH_EMAILS.put(uid, email)
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

    def is_first_invite(self, company_id: str) -> bool:
        """True while a company has no active member and no pending invite yet - the
        only moment an invite may be for the Head of Sales (owner) rather than a rep
        (founder request: the first account of a company is always the Head of Sales)."""
        return self.count_active_members(company_id) == 0 and not self.list_pending_invites(company_id)

    async def create_invite(
        self,
        *,
        company_id: str,
        email: str,
        role: str,
        invited_by: Optional[str] = None,
        send_email: bool = True,
        sales_role: Optional[str] = None,
    ) -> Tuple[dict, Optional[str], bool, Optional[bool]]:
        if role == "owner":
            if not self.is_first_invite(company_id):
                raise HTTPException(
                    status_code=400,
                    detail="This company already has a Head of Sales",
                )
        elif role not in INVITE_ROLES:
            raise HTTPException(status_code=400, detail="Invalid invite role")
        if sales_role is not None and sales_role not in SALES_ROLES:
            raise HTTPException(status_code=400, detail="Invalid sales_role")
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
        # Column only exists after migration 054; omit rather than send when unused so
        # invites keep working before it is applied.
        if sales_role:
            row["sales_role"] = sales_role
        result = self.supabase.table("company_invitations").insert(row).execute()
        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to create invite")
        invite = result.data[0]
        company = self.get_company(company_id)
        invite_url = f"{settings.FRONTEND_URL.rstrip('/')}/invite/{raw_token}"

        # Item 3: never blocks the invite - None means no connected CRM or a failed lookup.
        try:
            from app.services.invite_crm_match import crm_owner_match_for_invite

            crm_owner_match = crm_owner_match_for_invite(self.supabase, company_id, email_norm)
        except Exception as exc:
            logger.warning("crm_owner_match lookup failed for invite to %s: %s", email_norm, exc)
            crm_owner_match = None

        email_sent = False
        if send_email:
            inviter_name = self._display_name_for(invited_by) if invited_by else None
            email_sent = await self._send_invite_email(
                to=email_norm,
                company_name=company.get("name") or "Vocify",
                invite_url=invite_url,
                sales_role=sales_role,
                inviter_name=inviter_name,
            )
        return invite, invite_url if not email_sent else None, email_sent, crm_owner_match

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
            sales_role=invite.get("sales_role"),
        )
        return invite, invite_url if not email_sent else None, email_sent

    def _display_name_for(self, user_id: str) -> Optional[str]:
        """Best-effort inviter name for the invite email (item 4). Never raises."""
        try:
            result = (
                self.supabase.table("user_profiles")
                .select("full_name")
                .eq("id", user_id)
                .limit(1)
                .execute()
            )
            rows = result.data or []
            if rows and rows[0].get("full_name"):
                return str(rows[0]["full_name"])
        except Exception as exc:
            logger.warning("Could not resolve inviter name for %s: %s", user_id, exc)
        emails = self._auth_emails_by_ids([user_id])
        return emails.get(user_id) or None

    async def _send_invite_email(
        self,
        *,
        to: str,
        company_name: str,
        invite_url: str,
        sales_role: Optional[str] = None,
        inviter_name: Optional[str] = None,
    ) -> bool:
        client = get_resend_client()
        if not client:
            logger.warning("Resend not configured; invite email skipped for %s", to)
            return False
        html = build_invite_email_html(
            company_name=company_name,
            invite_url=invite_url,
            expires_days=INVITE_TOKEN_EXPIRY_DAYS,
            sales_role=sales_role,
            inviter_name=inviter_name,
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
        sales_role = invite.get("sales_role")

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

        member_row = {
            "company_id": company_id,
            "user_id": user_id,
            "role": role,
            "status": "active",
        }
        # Column only exists after migration 054; omit rather than send when unused so
        # invite acceptance keeps working before it is applied.
        if sales_role:
            member_row["sales_role"] = sales_role
        self.supabase.table("company_members").insert(member_row).execute()
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

    def update_member_profile(
        self,
        *,
        company_id: str,
        actor: Membership,
        member_id: str,
        sales_role: Optional[str] = "__unset__",
        handoff_ae_user_id: Optional[str] = "__unset__",
        visibility: Optional[str] = "__unset__",
    ) -> dict:
        """D1/D2/D3: commercial type, SDR->AE routing and activity visibility.

        Owner/admin only. A sentinel default tells "not provided" apart from
        "explicitly cleared to null", since every field here is optional.
        """
        if not actor.can_manage_team:
            raise HTTPException(status_code=403, detail="Only owners and admins can edit member profiles")

        target = self._get_member_row(company_id, member_id)
        updates: Dict[str, Any] = {}

        release_ae_side = False
        if sales_role != "__unset__":
            if sales_role is not None and sales_role not in SALES_ROLES:
                raise HTTPException(status_code=400, detail="Invalid sales_role")
            updates["sales_role"] = sales_role
            # An AE/General turned SDR no longer has a deals section: the contacts handed
            # to them go back to their SDRs and nobody stays routed to them.
            release_ae_side = sales_role == "sdr" and target.get("sales_role") != "sdr"

        if visibility != "__unset__":
            if visibility is not None and visibility not in VISIBILITIES:
                raise HTTPException(status_code=400, detail="Invalid visibility")
            updates["visibility"] = visibility or "own"

        if handoff_ae_user_id != "__unset__":
            if handoff_ae_user_id:
                if str(handoff_ae_user_id) == str(target["user_id"]):
                    raise HTTPException(status_code=400, detail="A rep cannot route handoffs to themselves")
                ae_row = self._get_member_row_by_user_id(company_id, str(handoff_ae_user_id))
                if (ae_row.get("status") or "active") != "active":
                    raise HTTPException(
                        status_code=400,
                        detail="handoff_ae_user_id must be an active member",
                    )
                ae_sales_role = ae_row.get("sales_role")
                # D1: a null sales_role behaves as "general".
                if ae_sales_role not in (None, "ae", "general"):
                    raise HTTPException(
                        status_code=400,
                        detail="handoff_ae_user_id must belong to an AE or general rep in this company",
                    )
                updates["handoff_ae_user_id"] = str(handoff_ae_user_id)
            else:
                updates["handoff_ae_user_id"] = None

        if not updates:
            return target

        updates["updated_at"] = _iso(_now())
        result = (
            self.supabase.table("company_members")
            .update(updates)
            .eq("id", member_id)
            .eq("company_id", company_id)
            .execute()
        )
        if release_ae_side:
            self._release_handoffs(company_id, str(target["user_id"]), as_ae_only=True)
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

        self._release_handoffs(company_id, str(target["user_id"]))
        self.supabase.table("company_members").delete().eq("id", member_id).execute()
        self.supabase.table("user_profiles").update({"company_id": None}).eq(
            "id", target["user_id"]
        ).execute()

    def _release_handoffs(self, company_id: str, user_id: str, *, as_ae_only: bool = False) -> None:
        """Lista 3: a leaving member (or one who stops being an AE) never keeps contacts
        locked in a handoff nobody can see. Never blocks the removal itself."""
        from app.services.handoffs import release_member_handoffs

        try:
            release_member_handoffs(self.supabase, company_id=company_id, user_id=user_id, as_ae_only=as_ae_only)
        except Exception:
            logger.warning("Releasing handoffs failed for user %s", user_id, exc_info=True)

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

    def _get_member_row_by_user_id(self, company_id: str, user_id: str) -> dict:
        # limit(1) rather than single(): single() raises (500) on zero rows, and a
        # non-member handoff_ae_user_id is an ordinary 400, not a server error.
        result = (
            self.supabase.table("company_members")
            .select("*")
            .eq("user_id", user_id)
            .eq("company_id", company_id)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        if not rows:
            raise HTTPException(status_code=400, detail="handoff_ae_user_id is not a member of this company")
        return rows[0]

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

    def update_callback_after_days(self, company_id: str, days: int) -> None:
        """T5: owner/admin only (require_manage_role at the API layer), 1-30 days (validated
        by the request model). Tolerant of migration 057 not having run yet: logged, and
        Hoy keeps using the default."""
        try:
            (
                self.supabase.table("companies")
                .update({"callback_after_days": int(days), "updated_at": _iso(_now())})
                .eq("id", company_id)
                .execute()
            )
        except Exception:
            logger.warning("callback_after_days not saved for %s (migration 057?)", company_id, exc_info=True)

    def update_followup_cadence(self, company_id: str, overrides: dict[str, int]) -> None:
        """Lista 4 T4: owner/admin only (require_manage_role at the API layer), validated by
        the request model. {} stores NULL (E8's defaults). Tolerant of migration 062 not
        having run yet, like update_callback_after_days."""
        try:
            (
                self.supabase.table("companies")
                .update({"followup_cadence": dict(overrides) or None, "updated_at": _iso(_now())})
                .eq("id", company_id)
                .execute()
            )
        except Exception:
            logger.warning("followup_cadence not saved for %s (migration 062?)", company_id, exc_info=True)

    def update_sales_strategy(self, company_id: str, value: Optional[str]) -> dict:
        """D10: owner/admin only (require_manage_role at the API layer). Blank clears it.
        Tolerant of migration 058_sales_strategy.sql not having run yet."""
        text = (value or "").strip()
        try:
            result = (
                self.supabase.table("companies")
                .update({"sales_strategy": text or None, "updated_at": _iso(_now())})
                .eq("id", company_id)
                .execute()
            )
            return (result.data or [{}])[0]
        except Exception as exc:
            if _missing_sales_strategy_column(exc):
                logger.warning(
                    "sales_strategy unavailable (run migration 058_sales_strategy.sql): %s", exc,
                )
                return self.get_company(company_id)
            raise

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
        self._release_handoffs(company_id, str(target["user_id"]))
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
        self._release_handoffs(membership.company_id, user_id)
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
