"""Settings → AI agents: the workspace switches, each user's API key, the consent screen and connected apps.

The MCP server itself lives at /mcp (app/services/mcp/server.py) and its OAuth server at /oauth/* (services/mcp/
oauth.py). These routes are what the dashboard calls to manage access to them: the signed-in user answers a
consent request here, and lists or disconnects the apps they connected.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel

from app.deps import get_membership, get_supabase
from app.services import feature_flags
from app.services.company import CompanyService, Membership
from app.services.mcp import access, api_keys, oauth

router = APIRouter(prefix="/api/v1/mcp", tags=["mcp"])
oauth_router = APIRouter(prefix="/api/v1/oauth", tags=["oauth"])



class WorkspaceSettings(BaseModel):
    enabled: Optional[bool] = None
    transcripts_enabled: Optional[bool] = None


class ConsentRequest(BaseModel):
    action: Literal["approve", "deny"]


def _set_flag(supabase, company_id: str, flag: str, enabled: bool) -> None:
    supabase.table("company_feature_flags").upsert(
        {"company_id": company_id, "flag": flag, "enabled": enabled, "updated_at": datetime.now(timezone.utc).isoformat()},
        on_conflict="company_id,flag",
    ).execute()


def _members(supabase, membership: Membership) -> list[dict]:
    from app.services.activity_scope import author_display_name

    members = [
        m for m in CompanyService(supabase).list_members(membership.company_id)
        if m.get("user_id") and (m.get("status") or "active") == "active"
    ]
    keys = api_keys.keys_of(supabase, [str(m["user_id"]) for m in members])
    return [
        {
            "user_id": str(m["user_id"]),
            "name": author_display_name(m.get("full_name"), m.get("email")),
            "email": m.get("email") or None,
            **keys.get(str(m["user_id"]), {"has_key": False, "prefix": None, "created_at": None}),
        }
        for m in members
    ]


@router.get("/settings")
def get_settings(membership: Membership = Depends(get_membership), supabase=Depends(get_supabase)):
    """What Settings → AI agents shows. The member list (who has a key) is for owners and admins."""
    body = {
        "server_url": access.server_url(),
        "enabled": feature_flags.is_enabled(supabase, membership.company_id, access.FLAG),
        "transcripts_enabled": access.transcripts_allowed(supabase, membership.company_id),
        "can_manage": membership.can_manage_team,
        "key": api_keys.key_status(supabase, membership.user_id),
    }
    if membership.can_manage_team:
        body["members"] = _members(supabase, membership)
    return body


@router.patch("/settings")
def update_settings(
    payload: WorkspaceSettings,
    membership: Membership = Depends(get_membership),
    supabase=Depends(get_supabase),
):
    if not membership.can_manage_team:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    if payload.enabled is not None:
        _set_flag(supabase, membership.company_id, access.FLAG, payload.enabled)
    if payload.transcripts_enabled is not None:
        _set_flag(supabase, membership.company_id, access.TRANSCRIPTS_FLAG, payload.transcripts_enabled)
    feature_flags.clear_cache()  # this instance at once; others within the flag cache's 60 s
    return get_settings(membership=membership, supabase=supabase)


@router.post("/key")
def create_key(membership: Membership = Depends(get_membership), supabase=Depends(get_supabase)):
    """A new key replaces the caller's old one. It is returned once; only its hash is kept."""
    if not feature_flags.is_enabled(supabase, membership.company_id, access.FLAG):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="AI agent access is off for this workspace. An owner or admin can turn it on.",
        )
    return api_keys.generate_key(supabase, membership.user_id)


@router.delete("/key", status_code=status.HTTP_204_NO_CONTENT)
def delete_key(membership: Membership = Depends(get_membership), supabase=Depends(get_supabase)):
    api_keys.revoke_key(supabase, membership.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/members/{user_id}/key", status_code=status.HTTP_204_NO_CONTENT)
def delete_member_key(user_id: str, membership: Membership = Depends(get_membership), supabase=Depends(get_supabase)):
    if not membership.can_manage_team:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    members = {str(m.get("user_id")) for m in CompanyService(supabase).list_members(membership.company_id)}
    if user_id not in members:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    api_keys.revoke_key(supabase, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ----- OAuth: consent and connected apps -----------------------------------------------------------------


def _gone() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="This sign-in request expired. Start again from the app."
    )


@oauth_router.get("/authorizations/{authorization_id}")
def get_authorization(authorization_id: str, membership: Membership = Depends(get_membership)):
    """The app asking for access: its name, where it sends the user back, and whether we recognise it."""
    request = oauth.read_request(authorization_id)
    if request is None:
        raise _gone()
    return request


@oauth_router.post("/authorizations/{authorization_id}/consent")
def consent(
    authorization_id: str,
    payload: ConsentRequest,
    membership: Membership = Depends(get_membership),
    supabase=Depends(get_supabase),
):
    """{redirect_url}: back to the app with a code (allow) or an error (deny)."""
    if payload.action == "approve" and not feature_flags.is_enabled(supabase, membership.company_id, access.FLAG):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="AI agent access is off for this workspace. An owner or admin can turn it on.",
        )
    redirect_url = oauth.decide(authorization_id, membership.user_id, payload.action == "approve")
    if redirect_url is None:
        raise _gone()
    return {"redirect_url": redirect_url}


@oauth_router.get("/grants")
def list_grants(membership: Membership = Depends(get_membership), supabase=Depends(get_supabase)):
    """The apps this user connected by signing in."""
    return {"grants": oauth.list_grants(supabase, membership.user_id)}


@oauth_router.delete("/grants", status_code=status.HTTP_204_NO_CONTENT)
def revoke_grant(
    client_id: str = Query(..., min_length=1),
    membership: Membership = Depends(get_membership),
    supabase=Depends(get_supabase),
):
    """Disconnect an app (client_id is the id list_grants gave): its tokens stop working within 30 seconds."""
    oauth.revoke_grant(supabase, membership.user_id, client_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
