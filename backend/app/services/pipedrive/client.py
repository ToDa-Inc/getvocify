"""
Async HTTP client for Pipedrive REST.

v2 for deals/persons/orgs/search/fields/pipelines/stages/activities.
v1 for notes, users, activityTypes. Base is OAuth `api_domain`.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

from .exceptions import (
    PipedriveAuthError,
    PipedriveError,
    PipedriveNotFoundError,
    PipedriveRateLimitError,
    PipedriveValidationError,
)
from .oauth import refresh_tokens

logger = logging.getLogger(__name__)


def unwrap_data(payload: Any) -> Any:
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"]
    return payload


def unwrap_search_items(payload: Any) -> list[dict[str, Any]]:
    data = unwrap_data(payload)
    if isinstance(data, dict):
        items = data.get("items") or []
    elif isinstance(data, list):
        items = data
    else:
        items = []
    out: list[dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        item = it.get("item") if isinstance(it.get("item"), dict) else it
        if isinstance(item, dict):
            out.append(item)
    return out


class PipedriveClient:
    def __init__(
        self,
        api_domain: str,
        access_token: str,
        *,
        refresh_token: Optional[str] = None,
        connection_id: Optional[str] = None,
        supabase: Any = None,
        token_expires_at: Optional[datetime] = None,
    ) -> None:
        self.api_domain = api_domain.rstrip("/")
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
            "Accept": "application/json",
        }

    def _url(self, version: str, path: str) -> str:
        p = path if path.startswith("/") else f"/{path}"
        return f"{self.api_domain}/api/{version}{p}"

    async def _persist_tokens(
        self,
        access_token: str,
        refresh_token: Optional[str],
        expires_in: Optional[int],
        api_domain: Optional[str] = None,
    ) -> None:
        self.access_token = access_token
        if refresh_token:
            self.refresh_token = refresh_token
        if api_domain:
            self.api_domain = str(api_domain).rstrip("/")
        expires_at = None
        if expires_in is not None:
            expires_at = (datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))).isoformat()
            self.token_expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        if not self.supabase or not self.connection_id:
            return
        row: dict[str, Any] = {"access_token": access_token}
        if refresh_token:
            row["refresh_token"] = refresh_token
        if expires_at:
            row["token_expires_at"] = expires_at
        if api_domain:
            try:
                existing = (
                    self.supabase.table("crm_connections")
                    .select("metadata")
                    .eq("id", self.connection_id)
                    .maybe_single()
                    .execute()
                )
                meta = dict((existing.data or {}).get("metadata") or {}) if existing else {}
            except Exception:
                meta = {}
            meta["api_domain"] = str(api_domain).rstrip("/")
            host = urlparse(meta["api_domain"]).hostname or ""
            if host.endswith(".pipedrive.com"):
                meta["company_domain"] = host.split(".")[0]
            row["metadata"] = meta
        try:
            self.supabase.table("crm_connections").update(row).eq("id", self.connection_id).execute()
        except Exception as e:
            logger.warning("Failed to persist Pipedrive tokens: %s", e)

    async def refresh_if_needed(self) -> None:
        if not self.refresh_token:
            return
        if self.token_expires_at and self.token_expires_at > datetime.now(timezone.utc) + timedelta(minutes=2):
            return
        async with self._refresh_lock:
            if self.token_expires_at and self.token_expires_at > datetime.now(timezone.utc) + timedelta(minutes=2):
                return
            await self._do_refresh()

    async def _do_refresh(self) -> None:
        if not self.refresh_token:
            raise PipedriveAuthError("Missing refresh token", status_code=401)
        body = await refresh_tokens(self.refresh_token)
        await self._persist_tokens(
            body["access_token"],
            body.get("refresh_token") or self.refresh_token,
            body.get("expires_in"),
            body.get("api_domain"),
        )

    async def request(
        self,
        method: str,
        path: str,
        *,
        version: str = "v2",
        json_body: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
        retry_on_auth: bool = True,
        retry_on_rate: bool = True,
    ) -> Any:
        await self.refresh_if_needed()
        url = self._url(version, path)
        async with httpx.AsyncClient(timeout=60.0) as http:
            resp = await http.request(
                method,
                url,
                headers=self._headers(),
                json=json_body,
                params=params,
            )

        if resp.status_code == 401 and retry_on_auth and self.refresh_token:
            await self._do_refresh()
            async with httpx.AsyncClient(timeout=60.0) as http:
                resp = await http.request(
                    method,
                    self._url(version, path),
                    headers=self._headers(),
                    json=json_body,
                    params=params,
                )

        if resp.status_code == 429 and retry_on_rate:
            wait_s = _retry_after_seconds(resp)
            await asyncio.sleep(min(max(wait_s, 1), 30))
            async with httpx.AsyncClient(timeout=60.0) as http:
                resp = await http.request(
                    method,
                    self._url(version, path),
                    headers=self._headers(),
                    json=json_body,
                    params=params,
                )
            if resp.status_code == 429:
                raise PipedriveRateLimitError(
                    "Pipedrive rate limit exceeded",
                    status_code=429,
                    response_data={"raw": _safe_json(resp)},
                )

        if resp.status_code == 204 or not resp.content:
            return None
        body = _safe_json(resp)
        if 200 <= resp.status_code < 300:
            return body

        msg = _error_message(body, resp.text)
        if resp.status_code == 401:
            raise PipedriveAuthError(msg, status_code=401, response_data={"raw": body})
        if resp.status_code == 404:
            raise PipedriveNotFoundError(msg, status_code=404, response_data={"raw": body})
        if resp.status_code in (400, 422):
            raise PipedriveValidationError(msg, status_code=resp.status_code, response_data={"raw": body})
        raise PipedriveError(msg, status_code=resp.status_code, response_data={"raw": body})

    async def get(self, path: str, *, version: str = "v2", params: Optional[dict[str, Any]] = None) -> Any:
        return await self.request("GET", path, version=version, params=params)

    async def post(self, path: str, json_body: Optional[dict[str, Any]] = None, *, version: str = "v2") -> Any:
        return await self.request("POST", path, version=version, json_body=json_body)

    async def patch(self, path: str, json_body: dict[str, Any], *, version: str = "v2") -> Any:
        return await self.request("PATCH", path, version=version, json_body=json_body)


def _safe_json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except Exception:
        return {"message": resp.text or "Unknown error"}


def _error_message(body: Any, fallback: str) -> str:
    if isinstance(body, dict):
        for key in ("error", "error_info", "message"):
            val = body.get(key)
            if val:
                return str(val)
    return fallback or "Pipedrive request failed"


def _retry_after_seconds(resp: httpx.Response) -> float:
    reset = resp.headers.get("x-ratelimit-reset") or resp.headers.get("Retry-After")
    if not reset:
        return 2.0
    try:
        val = float(reset)
    except ValueError:
        return 2.0
    if val > 1_000_000_000:
        return max(1.0, val - datetime.now(timezone.utc).timestamp())
    return val
