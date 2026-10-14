"""Who is calling /mcp, and whether they may. One resolver for both credentials.

A bearer token is either a personal API key (`vk_…`, looked up by hash on user_profiles) or an access token
from Vocify's own OAuth server (services/mcp/oauth.py). Either way the request ends as the same user, and
every tool then reads through that user's membership. The tools never know which credential was used.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass
from threading import Lock
from typing import Any, Optional

import anyio

from app.config import settings
from app.services.mcp import api_keys
from app.services.ttl_cache import TtlCache

logger = logging.getLogger(__name__)

FLAG = "MCP_ENABLED"
TRANSCRIPTS_FLAG = "MCP_TRANSCRIPTS_ENABLED"
_paywalled: TtlCache[bool] = TtlCache(60.0)


class AccessDenied(Exception):
    """The caller is known but may not use MCP right now. The message is for the agent to relay."""


def server_url() -> str:
    return settings.BACKEND_PUBLIC_URL.rstrip("/") + "/mcp"


def issuer_url() -> str:
    """The OAuth issuer is the API itself (services/mcp/oauth.py)."""
    return settings.BACKEND_PUBLIC_URL.rstrip("/")


def resolve_token(supabase: Any, token: str) -> Optional[tuple[str, str]]:
    """(user_id, credential) where credential is "api_key" or "oauth:<app name>". None means 401."""
    token = (token or "").strip()
    if not token:
        return None
    if api_keys.is_api_key(token):
        try:
            user_id = api_keys.user_for_key(supabase, token)
        except Exception:  # noqa: BLE001 - e.g. migration 079 not applied yet: no key is valid
            logger.warning("mcp api key lookup failed", exc_info=True)
            return None
        return (user_id, "api_key") if user_id else None
    from app.services.mcp import oauth

    found = oauth.verify_access_token(supabase, token)
    return (found[0], f"oauth:{found[1]}") if found else None


class VocifyTokenVerifier:
    """The MCP SDK's TokenVerifier: a failure is a 401 carrying the resource metadata pointer."""

    async def verify_token(self, token: str):
        from mcp.server.auth.provider import AccessToken

        from app.deps import get_supabase

        found = await anyio.to_thread.run_sync(resolve_token, get_supabase(), token)
        if not found:
            return None
        user_id, credential = found
        return AccessToken(token=token, client_id=credential, scopes=[], subject=user_id)


def require_membership(supabase: Any, user_id: str):
    """The caller's active membership, with MCP on for the workspace and the plan in good standing."""
    from app.services.billing.entitlement import is_paywalled
    from app.services.billing.store import get_billing
    from app.services.company import CompanyService
    from app.services.feature_flags import is_enabled

    service = CompanyService(supabase)
    membership = service.get_membership(user_id)
    if not membership or not membership.is_active:
        raise AccessDenied("This account has no active Vocify workspace. Ask your workspace admin to add you again.")
    if not is_enabled(supabase, membership.company_id, FLAG):
        raise AccessDenied(
            "Vocify's AI agent access is turned off for this workspace. An owner or admin can turn it on in "
            "Vocify: Settings → AI agents."
        )
    blocked = _paywalled.get(membership.company_id)
    if blocked is None:
        blocked = is_paywalled(service.get_company(membership.company_id), get_billing(supabase, membership.company_id))
        _paywalled.put(membership.company_id, blocked)
    if blocked:
        raise AccessDenied("This Vocify workspace's plan needs a payment. An owner can update billing in Vocify.")
    return membership


def actor_visibility(supabase: Any, membership) -> Optional[str]:
    """Same rule as the web Ask (api.ask._bind): only `team`, once the company allows it, widens a member's view."""
    from app.services.activity_scope import effective_visibility

    if getattr(membership, "visibility", None) != "team":
        return None
    try:
        return effective_visibility(supabase, membership)
    except Exception:  # noqa: BLE001 - unreadable means the narrower, owner/admin-only view
        return None


def actor_for(supabase: Any, membership):
    from app.services.crm_copilot.actor import AskActor

    return AskActor(
        user_id=membership.user_id,
        company_id=membership.company_id,
        role=membership.role,
        visibility=actor_visibility(supabase, membership),
        sales_role=getattr(membership, "sales_role", None),
    )


def transcripts_allowed(supabase: Any, company_id: str) -> bool:
    from app.services.feature_flags import is_enabled

    return is_enabled(supabase, company_id, TRANSCRIPTS_FLAG)


@dataclass
class _Window:
    calls: deque
    lock: Lock


_windows: dict[str, _Window] = {}
_windows_lock = Lock()


def check_rate(user_id: str, *, per_minute: Optional[int] = None, now: Optional[float] = None) -> None:
    """At most N tool calls per user per rolling minute, in this process. Raises AccessDenied with the wait."""
    limit = per_minute if per_minute is not None else settings.MCP_TOOL_CALLS_PER_MINUTE
    at = time.monotonic() if now is None else now
    with _windows_lock:
        window = _windows.setdefault(user_id, _Window(deque(), Lock()))
    with window.lock:
        while window.calls and at - window.calls[0] >= 60.0:
            window.calls.popleft()
        if len(window.calls) >= limit:
            wait = max(1, int(60.0 - (at - window.calls[0])) + 1)
            raise AccessDenied(f"Too many Vocify requests: the limit is {limit} per minute. Retry in {wait} seconds.")
        window.calls.append(at)


def reset_rate_limits() -> None:
    with _windows_lock:
        _windows.clear()
