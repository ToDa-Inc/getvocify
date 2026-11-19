"""Composio (REST v3.1): the rep connects Google Calendar through Composio's own Google app, so
Vocify's Google app needs no verification. Composio keeps the tokens; we only call Google
through its proxy with the rep's connected account. Docs: docs.composio.dev/reference.

- Connect Link: ``POST /connected_accounts/link`` with ``auth_config_id``, ``user_id`` (the
  Vocify user ID) and ``callback_url`` -> ``redirect_url`` and ``connected_account_id``.
- Accounts: ``GET /connected_accounts?user_ids=..&auth_config_ids=..&statuses=ACTIVE``,
  ``DELETE /connected_accounts/{id}``.
- Proxy: ``POST /tools/execute/proxy`` with ``connected_account_id``, ``user_id`` (required
  while the project has 2FA on), ``endpoint`` (absolute Google URL), ``method`` and query
  ``parameters`` -> ``{data, status}``.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://backend.composio.dev/api/v3.1"
_TIMEOUT_SECONDS = 30.0


class ComposioError(Exception):
    pass


class ComposioClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.COMPOSIO_API_KEY

    async def _call(self, method: str, path: str, *, what: str, **kwargs: Any) -> Any:
        if not self.api_key:
            raise ComposioError("COMPOSIO_API_KEY is not configured")
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.request(
                method, f"{BASE_URL}{path}", headers={"x-api-key": self.api_key}, **kwargs
            )
        if response.status_code >= 400:
            raise ComposioError(f"Composio {what} error {response.status_code}: {response.text[:500]}")
        return response.json() if response.content else None

    async def create_link(self, *, auth_config_id: str, user_id: str, callback_url: str) -> dict[str, Any]:
        return await self._call(
            "POST",
            "/connected_accounts/link",
            what="create link",
            json={"auth_config_id": auth_config_id, "user_id": user_id, "callback_url": callback_url},
        )

    async def active_accounts(self, *, auth_config_id: str, user_id: str) -> list[dict[str, Any]]:
        """The user's ACTIVE accounts on that auth config, newest first."""
        data = await self._call(
            "GET",
            "/connected_accounts",
            what="list accounts",
            params={
                "auth_config_ids": auth_config_id,
                "user_ids": user_id,
                "statuses": "ACTIVE",
                "order_by": "created_at",
                "order_direction": "desc",
                "limit": 20,
            },
        )
        return list((data or {}).get("items") or [])

    async def delete_account(self, account_id: str) -> None:
        await self._call("DELETE", f"/connected_accounts/{account_id}", what="delete account")

    async def proxy_get(
        self, account_id: str, user_id: str, endpoint: str, params: dict[str, str]
    ) -> dict[str, Any]:
        """GET on the provider's API as the account. Raises on the provider's own errors too."""
        data = await self._call(
            "POST",
            "/tools/execute/proxy",
            what="proxy",
            json={
                "connected_account_id": account_id,
                "user_id": user_id,
                "endpoint": endpoint,
                "method": "GET",
                "parameters": [{"name": k, "value": v, "type": "query"} for k, v in params.items()],
            },
        )
        status = int((data or {}).get("status") or 0)
        if status >= 400:
            raise ComposioError(f"Google {endpoint} error {status}: {str((data or {}).get('data'))[:500]}")
        return (data or {}).get("data") or {}
