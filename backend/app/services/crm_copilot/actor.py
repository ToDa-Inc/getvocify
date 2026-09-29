"""Who is asking. Immutable, one per request, taken from the session and never from the words."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Optional

from app.services.activity_scope import can_view_company_activity

TEAM_ROLES = frozenset({"owner", "admin"})


class ScopeError(Exception):
    """The actor asked for data outside their scope (or no actor was bound)."""


@dataclass(frozen=True)
class AskActor:
    user_id: str
    company_id: str
    role: str = "member"
    conversation_id: Optional[str] = None
    locale: str = "es"
    timezone: str = "Europe/Madrid"
    visibility: Optional[str] = None  # company_members.visibility, once SALES_ROLES_ENABLED
    sales_role: Optional[str] = None  # sdr | ae | general
    progress_key: Optional[tuple] = None  # where a polled POST reports its steps

    @property
    def is_team_reader(self) -> bool:
        """The same rule as the rest of the app: owners and admins, and members granted team visibility."""
        return can_view_company_activity(self.role, self.visibility)


_current: ContextVar[Optional[AskActor]] = ContextVar("ask_actor", default=None)


def bind_actor(actor: AskActor) -> None:
    _current.set(actor)


def current_actor() -> AskActor:
    actor = _current.get()
    if actor is None:
        raise ScopeError("no actor bound to this request")
    return actor


def visible_user_ids(actor: AskActor, company_service, requested_user_id: Optional[str] = None) -> list[str]:
    """Members see themselves. Owners and admins see the company or one member of it."""
    requested = (requested_user_id or "").strip() or None
    if not actor.is_team_reader:
        if requested and requested != actor.user_id:
            raise ScopeError("team data is not available to this role")
        return [actor.user_id]
    members = [
        str(m["user_id"])
        for m in company_service.list_members(actor.company_id)
        if m.get("user_id") and (m.get("status") or "active") == "active"
    ]
    if requested:
        if requested not in members:
            raise ScopeError("that user is not in this company")
        return [requested]
    return members
