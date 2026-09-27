"""Who is asking. Company and role come from company_members, never from the chat."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from app.services.activity_scope import (
    author_display_name,
    can_view_company_activity,
    load_viewer_scope,
    memo_readable_by,
)


@dataclass(frozen=True)
class Viewer:
    user_id: str
    company_id: str
    role: str
    members: tuple
    visibility: Optional[str] = None
    # T4/D8: contact_id -> sdr_user_id for every handoff (active or closed) to this
    # viewer as AE. Empty unless HANDOFF_ENABLED - see resolve_viewer.
    handoff_sdr_ids: dict = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.handoff_sdr_ids is None:
            object.__setattr__(self, "handoff_sdr_ids", {})

    @property
    def is_manager(self) -> bool:
        return can_view_company_activity(self.role, self.visibility)

    @property
    def member_ids(self) -> list[str]:
        return [
            str(member["user_id"])
            for member in self.members
            if member.get("user_id") and (member.get("status") or "active") == "active"
        ]

    def is_member(self, user_id: Optional[str]) -> bool:
        return bool(user_id) and str(user_id) in set(self.member_ids)

    def author_name(self, user_id: Optional[str]) -> Optional[str]:
        for member in self.members:
            if str(member.get("user_id") or "") == str(user_id or ""):
                return author_display_name(member.get("full_name"), member.get("email"))
        return None

    def readable_user_ids(self) -> list[str]:
        """Members read their own memos. Owners and admins read every active member's."""
        ids = {self.user_id, *self.member_ids}
        return sorted(
            uid
            for uid in ids
            if memo_readable_by(
                viewer_id=self.user_id,
                owner_user_id=uid,
                viewer_role=self.role,
                same_company=uid in set(self.member_ids),
                viewer_visibility=self.visibility,
            )
        )

    def readable_user_ids_for_contact(self, contact_id: Optional[str]) -> list[str]:
        """readable_user_ids(), plus the SDR who handed this contact off to me (T4/D8) -
        never a broader read, since a caller only widens with this when it also filters
        the read to that exact contact_id."""
        ids = set(self.readable_user_ids())
        sdr_id = self.handoff_sdr_ids.get(str(contact_id)) if contact_id else None
        if sdr_id:
            ids.add(sdr_id)
        return sorted(ids)


def resolve_viewer(ctx: Any) -> Optional[Viewer]:
    cached = getattr(ctx, "viewer", None)
    if isinstance(cached, Viewer):
        return cached
    user_id = str(getattr(ctx, "user_id", "") or "")
    supabase = getattr(ctx, "supabase", None)
    if not user_id or supabase is None:
        return None
    try:
        membership, members, _authors = load_viewer_scope(supabase, user_id)
    except Exception:
        return None
    if membership is None or not membership.is_active or not membership.company_id:
        return None
    from app.services.activity_scope import effective_visibility
    from app.services.handoff_visibility import handoff_sdr_ids_for_viewer

    company_id = str(membership.company_id)
    try:
        handoff_sdr_ids = handoff_sdr_ids_for_viewer(supabase, company_id=company_id, viewer_id=user_id)
    except Exception:
        handoff_sdr_ids = {}

    viewer = Viewer(
        user_id=user_id,
        company_id=company_id,
        role=str(membership.role or "member"),
        members=tuple(members or ()),
        visibility=effective_visibility(supabase, membership),
        handoff_sdr_ids=handoff_sdr_ids,
    )
    try:
        ctx.viewer = viewer
    except Exception:
        pass
    return viewer
