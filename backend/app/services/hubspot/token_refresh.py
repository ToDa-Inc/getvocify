"""
Refresh HubSpot OAuth access tokens stored on crm_connections.

Private App tokens (pat-...) are not refreshed — the user must rotate them in HubSpot.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx
from supabase import Client

from app.services.hubspot.oauth import oauth_enabled, refresh_access_token

logger = logging.getLogger(__name__)


def _is_hubspot_private_app_token(access_token: str) -> bool:
    t = (access_token or "").strip()
    return bool(t.startswith("pat-") or t.startswith("pat-na1-"))


def _parse_token_expires_at(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        s = raw.replace("Z", "+00:00")
        d = datetime.fromisoformat(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d
    except Exception:
        return None


def hubspot_oauth_access_token_is_stale(connection: dict[str, Any]) -> bool:
    """
    True if this HubSpot connection uses OAuth (not Private App) and the access
    token is missing expiry, expired, or within the refresh skew window.
    """
    access = connection.get("access_token") or ""
    if _is_hubspot_private_app_token(access):
        return False
    refresh = connection.get("refresh_token")
    if not refresh:
        return False
    exp = _parse_token_expires_at(connection.get("token_expires_at"))
    if exp is None:
        return True
    skew = timedelta(minutes=2)
    return datetime.now(timezone.utc) >= (exp - skew)


async def ensure_hubspot_connection_tokens_fresh(
    supabase: Client,
    connection: dict[str, Any],
) -> dict[str, Any]:
    """
    If the row is HubSpot OAuth and the access token is stale, refresh and persist.

    Returns the same connection dict with updated access_token (and possibly
    refresh_token) when a refresh runs; otherwise returns the input unchanged.
    """
    conn = dict(connection)
    if not hubspot_oauth_access_token_is_stale(conn):
        return conn
    if not oauth_enabled():
        logger.warning("HubSpot OAuth token stale but client credentials not configured; cannot refresh")
        return conn

    rt = conn.get("refresh_token")
    if not rt:
        return conn

    try:
        data = await refresh_access_token(str(rt))
    except httpx.HTTPStatusError as e:
        logger.warning(
            "HubSpot OAuth refresh failed: %s %s",
            e.response.status_code,
            e.response.text[:500] if e.response is not None else "",
        )
        raise ValueError(
            "HubSpot authorization expired or was revoked. Disconnect and reconnect HubSpot in Integrations."
        ) from e
    except Exception as e:
        logger.exception("HubSpot OAuth refresh error")
        raise ValueError(
            "Could not refresh HubSpot session. Try reconnecting in Integrations."
        ) from e

    new_access = data.get("access_token")
    if not new_access:
        raise ValueError("HubSpot token refresh returned no access_token")
    new_refresh = data.get("refresh_token") or rt
    expires_in = int(data.get("expires_in", 1800))
    new_expires = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()
    cid = conn["id"]

    supabase.table("crm_connections").update(
        {
            "access_token": new_access,
            "refresh_token": new_refresh,
            "token_expires_at": new_expires,
        }
    ).eq("id", str(cid)).execute()

    conn["access_token"] = new_access
    conn["refresh_token"] = new_refresh
    conn["token_expires_at"] = new_expires
    logger.info(
        "HubSpot OAuth access token refreshed",
        extra={"connection_id": str(cid)},
    )
    return conn
