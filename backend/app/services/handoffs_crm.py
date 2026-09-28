"""CRM owner effect of an SDR->AE handoff (T3, D7). Behind HANDOFF_CRM_OWNER_ENABLED.

find_owner_id reuses the exact owner id<->email mapping hoy/assigned.py already builds for
the assigned-contacts read - owners_request for the provider request shape and
connection_assigned_fetch for auth/retries/url-building - just inverted (looked up by email
instead of collected by id). set_owner is the small write half, one adapter method per
provider, matching CRMOwnerWriteProtocol.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

import httpx

from app.services.hoy.assigned import connection_assigned_fetch, owners_request

logger = logging.getLogger(__name__)

_MAX_PAGES = 50
_HUBSPOT_BASE = "https://api.hubapi.com"
_TIMEOUT = 30.0


def find_owner_id(fetch: Callable[[dict], dict], provider: str, email: str) -> Optional[str]:
    """The provider's owner id whose email matches (case-insensitive, exact)."""
    needle = (email or "").strip().lower()
    if not needle:
        return None
    cursor = None
    for _ in range(_MAX_PAGES):
        payload = fetch(owners_request(provider, cursor)) or {}
        if payload.get("error_kind"):
            return None
        rows = payload.get("results") if provider == "hubspot" else payload.get("data")
        for owner in rows or []:
            if str(owner.get("email") or "").strip().lower() == needle and owner.get("id") is not None:
                return str(owner["id"])
        cursor = ((payload.get("paging") or {}).get("next") or {}).get("after") if provider == "hubspot" else None
        if not cursor:
            break
    return None


class CrmOwnerWriter:
    """Implements CRMOwnerWriteProtocol for HubSpot and Pipedrive using a connection token."""

    def __init__(
        self,
        *,
        provider: str,
        access_token: str,
        api_domain: Optional[str] = None,
        transport: httpx.BaseTransport | None = None,
        timeout: float = _TIMEOUT,
        fetch: Optional[Callable[[dict], dict]] = None,
    ) -> None:
        self._provider = provider
        self._access_token = access_token
        self._api_domain = (api_domain or "").rstrip("/")
        self._client = httpx.Client(transport=transport, timeout=timeout)
        self._fetch = fetch

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._access_token}", "Content-Type": "application/json"}

    def find_owner_id(self, email: str) -> Optional[str]:
        fetch = self._fetch or connection_assigned_fetch(
            {"provider": self._provider, "access_token": self._access_token, "metadata": {"api_domain": self._api_domain}},
            client=self._client,
        )
        return find_owner_id(fetch, self._provider, email)

    def set_owner(self, *, object_type: str, object_id: str, owner_id: str) -> bool:
        """object_type: 'deal' or 'contact'. Returns False rather than raising - a failed
        CRM write leaves the handoff itself intact (D7: crm_owner_status='failed')."""
        try:
            if self._provider == "hubspot":
                path = "deals" if object_type == "deal" else "contacts"
                url = f"{_HUBSPOT_BASE}/crm/v3/objects/{path}/{object_id}"
                response = self._client.patch(url, headers=self._headers(), json={"properties": {"hubspot_owner_id": owner_id}})
            elif self._provider == "pipedrive":
                path = "deals" if object_type == "deal" else "persons"
                url = f"{self._api_domain}/api/v2/{path}/{object_id}"
                owner_value: Any = int(owner_id) if str(owner_id).isdigit() else owner_id
                response = self._client.patch(url, headers=self._headers(), json={"owner_id": owner_value})
            else:
                return False
            return response.status_code < 400
        except httpx.HTTPError as exc:
            logger.warning("CRM owner write failed for %s %s: %s", self._provider, object_type, exc)
            return False


def owner_writer_from_connection(
    connection: dict[str, Any],
    *,
    transport: httpx.BaseTransport | None = None,
    timeout: float = _TIMEOUT,
) -> Optional[CrmOwnerWriter]:
    token = (connection.get("access_token") or "").strip()
    if not token:
        return None
    provider = (connection.get("provider") or "").strip().lower()
    if provider not in {"hubspot", "pipedrive"}:
        return None
    api_domain = None
    if provider == "pipedrive":
        meta = connection.get("metadata") or {}
        api_domain = (meta.get("api_domain") or "").rstrip("/") if isinstance(meta, dict) else ""
        if not api_domain:
            return None
    return CrmOwnerWriter(provider=provider, access_token=token, api_domain=api_domain, transport=transport, timeout=timeout)


def _user_email(supabase: Any, user_id: str) -> Optional[str]:
    try:
        auth_user = supabase.auth.admin.get_user_by_id(user_id)
    except Exception as exc:
        logger.warning("Could not resolve email for user %s: %s", user_id, exc)
        return None
    if not auth_user:
        return None
    user = getattr(auth_user, "user", auth_user)
    email = getattr(user, "email", None) or (user.get("email") if isinstance(user, dict) else None)
    return str(email).strip() if email else None


def apply_owner_handoff(
    supabase: Any,
    *,
    connection: dict[str, Any],
    ae_user_id: str,
    deal_id: Optional[str],
    contact_id: Optional[str],
    writer: Optional[CrmOwnerWriter] = None,
) -> str:
    """Writes the AE's mapped CRM owner onto the deal (or the contact, if there is no
    deal yet) - D7. Returns crm_owner_status: done / skipped / unmapped / failed."""
    writer = writer if writer is not None else owner_writer_from_connection(connection)
    if writer is None:
        return "skipped"
    object_id = deal_id or contact_id
    if not object_id:
        return "skipped"
    email = _user_email(supabase, ae_user_id)
    if not email:
        return "unmapped"
    owner_id = writer.find_owner_id(email)
    if not owner_id:
        return "unmapped"
    object_type = "deal" if deal_id else "contact"
    ok = writer.set_owner(object_type=object_type, object_id=str(object_id), owner_id=owner_id)
    return "done" if ok else "failed"
