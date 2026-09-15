"""Company activity visibility: who can see whose calls and memos."""

from __future__ import annotations

from typing import Optional

from supabase import Client

from app.services.company import CompanyService, Membership


class UnknownCompanyAuthor(ValueError):
    """author_user_id is not a member of the viewer's company."""


def can_view_company_activity(role: Optional[str]) -> bool:
    return (role or "") in ("owner", "admin")


def active_member_count(members: list[dict]) -> int:
    return sum(
        1
        for member in members
        if member.get("user_id") and (member.get("status") or "active") == "active"
    )


def should_apply_author_recording_filter(
    *,
    author_user_id: Optional[str],
    can_view_company: bool,
    members: list[dict],
) -> bool:
    """Mine filter is only meaningful when the author chip is on screen."""
    if not (author_user_id or "").strip() or not can_view_company:
        return False
    return active_member_count(members) > 1


def author_display_name(full_name: Optional[str], email: Optional[str]) -> str:
    name = (full_name or "").strip()
    if name:
        return name
    addr = (email or "").strip()
    if addr:
        return addr.split("@")[0]
    return "Teammate"


def authors_by_user_id(members: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for member in members:
        uid = str(member.get("user_id") or "")
        if not uid:
            continue
        email = member.get("email") or ""
        out[uid] = {
            "user_id": uid,
            "name": author_display_name(member.get("full_name"), email),
            "email": email,
        }
    return out


def company_user_ids(members: list[dict]) -> list[str]:
    return [str(m["user_id"]) for m in members if m.get("user_id")]


def resolve_list_user_ids(
    *,
    viewer_id: str,
    viewer_role: Optional[str],
    member_ids: list[str],
    scope: str = "me",
    author_user_id: Optional[str] = None,
) -> list[str]:
    """User ids a list endpoint may return.

    Members always get themselves. Owners/admins with scope=company get the
    company (or one teammate when author_user_id is set).
    """
    scope_norm = (scope or "me").strip().lower()
    if scope_norm not in ("me", "company"):
        scope_norm = "me"
    if scope_norm == "company" and can_view_company_activity(viewer_role):
        allowed = set(member_ids) or {viewer_id}
        if author_user_id:
            if author_user_id not in allowed:
                raise UnknownCompanyAuthor(author_user_id)
            return [author_user_id]
        return list(allowed)
    return [viewer_id]


def memo_readable_by(
    *,
    viewer_id: str,
    owner_user_id: str,
    viewer_role: Optional[str],
    same_company: bool,
) -> bool:
    if viewer_id == owner_user_id:
        return True
    return bool(can_view_company_activity(viewer_role) and same_company)


def invert_hubspot_owners(meta: Optional[dict]) -> dict[str, str]:
    """HubSpot owner id → Vocify user id from connection metadata."""
    owners = (meta or {}).get("hubspot_owners")
    if not isinstance(owners, dict):
        return {}
    out: dict[str, str] = {}
    for uid, hid in owners.items():
        if hid:
            out[str(hid)] = str(uid)
    return out


def annotate_recording_author(
    recording: dict,
    authors: dict[str, dict],
    owner_to_user: dict[str, str],
) -> dict:
    hid = recording.get("hubspot_owner_id")
    uid = owner_to_user.get(str(hid)) if hid else None
    author = authors.get(uid) if uid else None
    return {
        **recording,
        "author_user_id": author["user_id"] if author else None,
        "author_name": author["name"] if author else None,
        "author_email": author["email"] if author else None,
    }


def visible_recordings_for_viewer(
    recordings: list[dict],
    *,
    viewer_id: str,
    can_view_company: bool,
) -> list[dict]:
    if can_view_company:
        return recordings
    return [row for row in recordings if row.get("author_user_id") == viewer_id]


def load_viewer_scope(
    supabase: Client,
    user_id: str,
) -> tuple[Optional[Membership], list[dict], dict[str, dict]]:
    svc = CompanyService(supabase)
    membership = svc.get_membership(user_id)
    if not membership:
        return None, [], {}
    members = svc.list_members(membership.company_id)
    return membership, members, authors_by_user_id(members)
