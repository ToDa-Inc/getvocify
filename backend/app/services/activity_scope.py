"""Company activity visibility: who can see whose calls and memos."""

from __future__ import annotations

from typing import Optional

from supabase import Client

from app.services.company import CompanyService, Membership


class UnknownCompanyAuthor(ValueError):
    """author_user_id is not a member of the viewer's company."""


def can_view_company_activity(role: Optional[str], visibility: Optional[str] = None) -> bool:
    """Owners/admins always see company activity; a member with visibility=team also does
    (read-only: it carries no management permission)."""
    if (role or "") in ("owner", "admin"):
        return True
    return (visibility or "") == "team"


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
    viewer_visibility: Optional[str] = None,
) -> list[str]:
    """User ids a list endpoint may return.

    Members always get themselves. Owners/admins (or a member with visibility=team)
    with scope=company get the company (or one teammate when author_user_id is set).
    """
    scope_norm = (scope or "me").strip().lower()
    if scope_norm not in ("me", "company"):
        scope_norm = "me"
    if scope_norm == "company" and can_view_company_activity(viewer_role, viewer_visibility):
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
    viewer_visibility: Optional[str] = None,
    handoff_sdr_id: Optional[str] = None,
) -> bool:
    """T4/D8: beyond your own and (with company visibility) your team's, an AE also reads a
    memo whose author is the SDR of a handoff for that memo's contact - handoff_sdr_id is
    that SDR's user_id, resolved by the caller from the memo's contact, or None when there
    is no such handoff (HANDOFF_ENABLED off, no row, or a different contact/SDR)."""
    if viewer_id == owner_user_id:
        return True
    if can_view_company_activity(viewer_role, viewer_visibility) and same_company:
        return True
    return bool(handoff_sdr_id) and handoff_sdr_id == owner_user_id


def readable_memo_or_none(
    memo_data: Optional[dict],
    *,
    viewer_id: str,
    viewer_role: Optional[str],
    member_ids: list[str],
    viewer_visibility: Optional[str] = None,
    handoff_sdr_ids: Optional[dict[str, str]] = None,
) -> Optional[dict]:
    """Return the memo row when the viewer may read it; else None.

    handoff_sdr_ids is contact_id -> sdr_user_id (T4/D8), scoped to the viewer as AE; the
    memo's own hubspot_contact_id picks out the one handoff (if any) that applies to it.
    """
    if not memo_data:
        return None
    owner_id = str(memo_data.get("user_id") or "")
    contact_id = str(memo_data.get("hubspot_contact_id") or "")
    handoff_sdr_id = (handoff_sdr_ids or {}).get(contact_id) if contact_id else None
    if not memo_readable_by(
        viewer_id=viewer_id,
        owner_user_id=owner_id,
        viewer_role=viewer_role,
        same_company=owner_id in set(member_ids),
        viewer_visibility=viewer_visibility,
        handoff_sdr_id=handoff_sdr_id,
    ):
        return None
    return memo_data


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


def effective_visibility(supabase: Client, membership: Optional[Membership]) -> Optional[str]:
    """membership.visibility, but only once SALES_ROLES_ENABLED — off means today's
    owner/admin-only behavior, whatever the column happens to hold."""
    if membership is None:
        return None
    from app.services.feature_flags import is_enabled

    if not is_enabled(supabase, membership.company_id, "SALES_ROLES_ENABLED"):
        return None
    return getattr(membership, "visibility", None)


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
