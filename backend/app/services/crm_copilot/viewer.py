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

    @property
    def is_manager(self) -> bool:
        return can_view_company_activity(self.role)

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
            )
        )


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
    viewer = Viewer(
        user_id=user_id,
        company_id=str(membership.company_id),
        role=str(membership.role or "member"),
        members=tuple(members or ()),
    )
    try:
        ctx.viewer = viewer
    except Exception:
        pass
    return viewer
