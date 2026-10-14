"""Settings → AI agents: the workspace switches, each user's API key, and the OAuth consent screen's calls.

The MCP server itself lives at /mcp (app/services/mcp/server.py). These routes are what the dashboard uses
to manage access to it. The OAuth ones forward to Supabase Auth's OAuth 2.1 server with the signed-in
user's own session token, the same calls supabase-js makes (`auth.oauth.*`), since the dashboard does not
use supabase-js.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from pydantic import BaseModel

from app.config import settings
from app.deps import get_membership, get_supabase, get_user_id
from app.services import feature_flags
from app.services.company import CompanyService, Membership
from app.services.mcp import access, api_keys

router = APIRouter(prefix="/api/v1/mcp", tags=["mcp"])
oauth_router = APIRouter(prefix="/api/v1/oauth", tags=["oauth"])

_GOTRUE_VERSION = {"X-Supabase-Api-Version": "2024-01-01"}


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


# ----- OAuth consent (Supabase Auth OAuth 2.1 server) ---------------------------------------------


def _bearer(authorization: Optional[str]) -> str:
    token = (authorization or "").replace("Bearer ", "", 1).strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization header")
    return token


async def _gotrue(method: str, path: str, token: str, *, json: Optional[dict] = None, params: Optional[dict] = None):
    apikey = (settings.SUPABASE_ANON_KEY or "").strip() or settings.SUPABASE_SERVICE_ROLE_KEY
    headers = {"apikey": apikey, "Authorization": f"Bearer {token}", **_GOTRUE_VERSION}
    url = settings.SUPABASE_URL.rstrip("/") + "/auth/v1" + path
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.request(method, url, headers=headers, json=json, params=params)
    except httpx.HTTPError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Sign-in service unavailable") from error
    if response.status_code >= 400:
        try:
            body = response.json()
        except ValueError:
            body = {}
        detail = body.get("msg") or body.get("message") or body.get("error_description") or "OAuth request failed"
        code = body.get("error_code") or body.get("code")
        raise HTTPException(status_code=response.status_code, detail={"message": detail, "code": code})
    if response.status_code == 204 or not response.content:
        return None
    return response.json()


@oauth_router.get("/authorizations/{authorization_id}")
async def get_authorization(
    authorization_id: str,
    _user_id: str = Depends(get_user_id),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    """The app asking for access, its redirect and scopes; or {redirect_url} when the user already consented."""
    return await _gotrue("GET", f"/oauth/authorizations/{authorization_id}", _bearer(authorization))


@oauth_router.post("/authorizations/{authorization_id}/consent")
async def consent(
    authorization_id: str,
    payload: ConsentRequest,
    _user_id: str = Depends(get_user_id),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    """{redirect_url} to send the browser back to the app, with a code (approve) or an error (deny)."""
    return await _gotrue(
        "POST", f"/oauth/authorizations/{authorization_id}/consent", _bearer(authorization), json={"action": payload.action}
    )


@oauth_router.get("/grants")
async def list_grants(
    _user_id: str = Depends(get_user_id),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    """The apps this user connected through OAuth."""
    body = await _gotrue("GET", "/user/oauth/grants", _bearer(authorization))
    return {"grants": body if isinstance(body, list) else (body or {}).get("grants", [])}


@oauth_router.delete("/grants", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_grant(
    client_id: str = Query(..., min_length=1),
    _user_id: str = Depends(get_user_id),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    await _gotrue("DELETE", "/user/oauth/grants", _bearer(authorization), params={"client_id": client_id})
    return Response(status_code=status.HTTP_204_NO_CONTENT)
