"""Fields AI can fill, per sales role and per person (migration 065_crm_field_permissions.sql).

The Head of Sales keeps one CRM configuration for the whole company (crm_configurations):
pipeline, stages, Skip Approve, create contacts/companies and the company field lists. On top
of the field lists only, they can say "an SDR fills these" (scope 'role') and, for one person,
"this rep fills these" (scope 'member'). Resolution is person -> role -> company, per object:
a NULL column inherits, an array (even empty) replaces.

Everything that reads the configuration for a rep goes through
CRMConfigurationService.get_configuration, which calls `field_overrides_for` here, so
extraction, previews, approve and the unattended writes all see the same fields.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from fastapi import HTTPException

logger = logging.getLogger(__name__)

TABLE = "crm_field_permissions"
SCOPE_ROLE = "role"
SCOPE_MEMBER = "member"
ROLE_KEYS: tuple[str, ...] = ("sdr", "ae", "general")
FIELD_KEYS: tuple[str, ...] = (
    "allowed_deal_fields",
    "allowed_contact_fields",
    "allowed_company_fields",
    "allowed_line_item_fields",
)


def _missing_table(exc: BaseException) -> bool:
    """True when migration 065 has not run yet: behave as if nobody had overrides."""
    msg = str(exc).lower()
    return TABLE in msg and ("does not exist" in msg or "could not find" in msg or "pgrst205" in msg)


def clean_field_list(value: Any) -> Optional[list[str]]:
    """None stays None (inherit). Anything else becomes a de-duplicated list of names."""
    if value is None:
        return None
    out: list[str] = []
    for item in value:
        name = str(item or "").strip()
        if name and name not in out:
            out.append(name)
    return out


def role_for_fields(
    *, sales_role: Optional[str], member_role: Optional[str], sales_roles_on: bool
) -> Optional[str]:
    """Which role's fields apply. A rep with no type is "general" (054: NULL = general);
    an owner/admin with no type is the Head of Sales, who uses the company's lists."""
    if not sales_roles_on:
        return None
    if sales_role in ROLE_KEYS:
        return sales_role
    if member_role in ("owner", "admin"):
        return None
    return "general"


def resolve_overrides(
    role_row: Optional[Mapping[str, Any]],
    member_row: Optional[Mapping[str, Any]],
) -> dict[str, list[str]]:
    """Person over role, independently for each object's list. Only the lists someone set
    are returned; a missing key means the company's list applies."""
    out: dict[str, list[str]] = {}
    for key in FIELD_KEYS:
        for row in (member_row, role_row):
            if row is not None and row.get(key) is not None:
                out[key] = list(row.get(key) or [])
                break
    return out


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rows_for(supabase: Any, connection_id: str, keys: list[str]) -> list[dict]:
    result = (
        supabase.table(TABLE)
        .select("*")
        .eq("connection_id", str(connection_id))
        .in_("scope_key", keys)
        .execute()
    )
    return list(getattr(result, "data", None) or [])


def field_overrides_for(supabase: Any, *, connection_id: str, user_id: str) -> dict[str, list[str]]:
    """The field lists set for `user_id` (their own, else their role's) on this CRM
    connection. Never raises: any failure (no membership, table not migrated, lookup error)
    returns {} - the company's lists apply."""
    from app.services.company import CompanyService

    try:
        svc = CompanyService(supabase)
        membership = svc.get_membership(user_id)
        if not membership or not membership.is_active:
            return {}
        role = role_for_fields(
            sales_role=membership.sales_role,
            member_role=membership.role,
            sales_roles_on=svc.sales_roles_enabled(membership.company_id),
        )
        keys = [str(user_id)] + ([role] if role else [])
        rows = _rows_for(supabase, connection_id, keys)
    except Exception as exc:
        if not _missing_table(exc):
            logger.warning("crm field permissions lookup failed for %s: %s", user_id, exc)
        return {}
    member_row = next(
        (r for r in rows if r.get("scope") == SCOPE_MEMBER and str(r.get("scope_key")) == str(user_id)),
        None,
    )
    role_row = next(
        (r for r in rows if role and r.get("scope") == SCOPE_ROLE and r.get("scope_key") == role),
        None,
    )
    return resolve_overrides(role_row, member_row)


def _public_row(row: Mapping[str, Any]) -> dict:
    return {key: row.get(key) for key in FIELD_KEYS}


def list_permissions(supabase: Any, *, connection_id: str) -> dict:
    """{"roles": {sdr|ae|general: {field lists | None}}, "members": {user_id: {...}}} for the
    Head of Sales' editor. Missing table reads as "nothing overridden yet"."""
    try:
        result = supabase.table(TABLE).select("*").eq("connection_id", str(connection_id)).execute()
        rows = list(getattr(result, "data", None) or [])
    except Exception as exc:
        if _missing_table(exc):
            rows = []
        else:
            raise
    roles: dict[str, Optional[dict]] = {key: None for key in ROLE_KEYS}
    members: dict[str, dict] = {}
    for row in rows:
        if row.get("scope") == SCOPE_ROLE and row.get("scope_key") in roles:
            roles[row["scope_key"]] = _public_row(row)
        elif row.get("scope") == SCOPE_MEMBER:
            members[str(row.get("scope_key"))] = _public_row(row)
    return {"roles": roles, "members": members}


def _validate_scope(scope: str, scope_key: str) -> None:
    if scope == SCOPE_ROLE:
        if scope_key not in ROLE_KEYS:
            raise HTTPException(status_code=400, detail="Invalid sales role")
    elif scope != SCOPE_MEMBER:
        raise HTTPException(status_code=400, detail="Invalid scope")


def save_permission(
    supabase: Any,
    *,
    company_id: str,
    connection_id: str,
    scope: str,
    scope_key: str,
    fields: Mapping[str, Any],
    updated_by: Optional[str],
) -> dict:
    """Upsert one role's or one person's lists. All four inherit (None) = the row is removed."""
    _validate_scope(scope, scope_key)
    cleaned = {key: clean_field_list(fields.get(key)) for key in FIELD_KEYS}
    if all(value is None for value in cleaned.values()):
        delete_permission(supabase, connection_id=connection_id, scope=scope, scope_key=scope_key)
        return cleaned
    row = {
        "company_id": str(company_id),
        "connection_id": str(connection_id),
        "scope": scope,
        "scope_key": str(scope_key),
        **cleaned,
        "updated_by": updated_by,
        "updated_at": _now_iso(),
    }
    try:
        result = (
            supabase.table(TABLE)
            .upsert(row, on_conflict="connection_id,scope,scope_key")
            .execute()
        )
    except Exception as exc:
        if _missing_table(exc):
            raise HTTPException(
                status_code=503,
                detail="Per-role fields need migration 065_crm_field_permissions.sql",
            ) from exc
        raise
    saved = (getattr(result, "data", None) or [row])[0]
    return _public_row(saved)


def delete_permission(supabase: Any, *, connection_id: str, scope: str, scope_key: str) -> None:
    _validate_scope(scope, scope_key)
    try:
        (
            supabase.table(TABLE)
            .delete()
            .eq("connection_id", str(connection_id))
            .eq("scope", scope)
            .eq("scope_key", str(scope_key))
            .execute()
        )
    except Exception as exc:
        if not _missing_table(exc):
            raise


def edits_company_fields(supabase: Any, user_id: str) -> bool:
    """The CRM settings screen: a Head of Sales (owner/admin) reads and saves the company's
    lists, so a manager who is also typed AE never sees - and re-saves - the AE lists as the
    company's. A rep sees the lists that apply to them."""
    from app.services.company import CompanyService

    try:
        membership = CompanyService(supabase).get_membership(user_id)
    except Exception:
        return True
    return bool(membership and membership.can_manage_team)
