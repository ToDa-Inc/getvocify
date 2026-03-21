"""
Async HTTP client for Salesforce REST API (per-org instance_url).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx

from app.config import settings

from .exceptions import SalesforceAuthError, SalesforceError, SalesforceValidationError

logger = logging.getLogger(__name__)

API_VERSION = "v59.0"


class SalesforceClient:
    def __init__(
        self,
        instance_url: str,
        access_token: str,
        *,
        refresh_token: Optional[str] = None,
        connection_id: Optional[str] = None,
        supabase: Any = None,
        token_expires_at: Optional[datetime] = None,
    ) -> None:
        self.instance_url = instance_url.rstrip("/")
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.connection_id = connection_id
        self.supabase = supabase
        self.token_expires_at = token_expires_at
        self._refresh_lock = asyncio.Lock()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    async def _persist_tokens(
        self,
        access_token: str,
        refresh_token: Optional[str],
        expires_in: Optional[int],
    ) -> None:
        if not self.supabase or not self.connection_id:
            return
        expires_at = None
        if expires_in:
            expires_at = (datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))).isoformat()
        row: dict[str, Any] = {"access_token": access_token}
        if refresh_token:
            row["refresh_token"] = refresh_token
        if expires_at:
            row["token_expires_at"] = expires_at
        try:
            self.supabase.table("crm_connections").update(row).eq("id", self.connection_id).execute()
        except Exception as e:
            logger.warning("Failed to persist Salesforce tokens: %s", e)
        self.access_token = access_token
        if refresh_token:
            self.refresh_token = refresh_token
        if expires_at:
            self.token_expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))

    async def refresh_if_needed(self) -> None:
        if not self.refresh_token or not settings.SALESFORCE_CLIENT_ID or not settings.SALESFORCE_CLIENT_SECRET:
            return
        if self.token_expires_at and self.token_expires_at > datetime.now(timezone.utc) + timedelta(minutes=2):
            return
        async with self._refresh_lock:
            if self.token_expires_at and self.token_expires_at > datetime.now(timezone.utc) + timedelta(minutes=2):
                return
            await self._do_refresh()

    async def _do_refresh(self) -> None:
        token_url = f"{settings.SALESFORCE_LOGIN_BASE.rstrip('/')}/services/oauth2/token"
        data = {
            "grant_type": "refresh_token",
            "client_id": settings.SALESFORCE_CLIENT_ID,
            "client_secret": settings.SALESFORCE_CLIENT_SECRET,
            "refresh_token": self.refresh_token,
        }
        async with httpx.AsyncClient(timeout=30.0) as http:
            resp = await http.post(token_url, data=data)
            if resp.status_code != 200:
                raise SalesforceAuthError(
                    f"Token refresh failed: {resp.text}",
                    status_code=resp.status_code,
                )
            body = resp.json()
        await self._persist_tokens(
            body["access_token"],
            body.get("refresh_token") or self.refresh_token,
            body.get("expires_in"),
        )

    def _url(self, path: str) -> str:
        p = path if path.startswith("/") else f"/{path}"
        return f"{self.instance_url}/services/data/{API_VERSION}{p}"

    async def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
        retry_on_auth: bool = True,
    ) -> Any:
        await self.refresh_if_needed()
        async with httpx.AsyncClient(timeout=60.0) as http:
            resp = await http.request(
                method,
                self._url(path),
                headers=self._headers(),
                json=json_body,
                params=params,
            )
        if resp.status_code == 401 and retry_on_auth and self.refresh_token:
            await self._do_refresh()
            async with httpx.AsyncClient(timeout=60.0) as http:
                resp = await http.request(
                    method,
                    self._url(path),
                    headers=self._headers(),
                    json=json_body,
                    params=params,
                )

        if resp.status_code == 204:
            return None
        if 200 <= resp.status_code < 300:
            if not resp.content:
                return None
            return resp.json()

        try:
            err = resp.json()
        except Exception:
            err = [{"message": resp.text or "Unknown error"}]
        msg = err[0].get("message", str(err)) if isinstance(err, list) else err.get("message", str(err))

        if resp.status_code == 401:
            raise SalesforceAuthError(msg, status_code=401, response_data={"raw": err})
        if resp.status_code == 404:
            from .exceptions import SalesforceNotFoundError

            raise SalesforceNotFoundError(msg, status_code=404, response_data={"raw": err})
        if resp.status_code == 400:
            raise SalesforceValidationError(msg, status_code=400, response_data={"raw": err})
        raise SalesforceError(msg, status_code=resp.status_code, response_data={"raw": err})

    async def get(self, path: str, params: Optional[dict[str, Any]] = None) -> Any:
        return await self.request("GET", path, params=params)

    async def post(self, path: str, json_body: Optional[dict[str, Any]] = None) -> Any:
        return await self.request("POST", path, json_body=json_body)

    async def patch(self, path: str, json_body: dict[str, Any]) -> Any:
        return await self.request("PATCH", path, json_body=json_body)
