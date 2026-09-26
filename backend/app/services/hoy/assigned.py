"""Turn one HubSpot or Pipedrive assigned-contacts page into a read envelope."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import httpx
from starlette.concurrency import run_in_threadpool

from app.services.crm_providers.coverage import from_provider_error, read_envelope

logger = logging.getLogger(__name__)

_HUBSPOT_BASE = "https://api.hubapi.com"
_ASSIGNED_TIMEOUT = 30.0
_ERROR_KINDS = {"401": "auth_expired", "403": "email_scope_missing"}
_HUBSPOT_PAGE = 200
_PIPEDRIVE_PAGE = 500
_MAX_PAGES = 200
_RATE_LIMIT_RETRIES = 3
_MAX_RETRY_WAIT = 10.0
_sleep = time.sleep


def _error_envelope(kind: str, *, connection_id: str, observed_at: str) -> dict:
    envelope = from_provider_error(
        _ERROR_KINDS.get(kind, kind),
        observed_at=observed_at,
        connection_id=connection_id,
        object_type="contact",
    )
    envelope["connection_id"] = connection_id
    return envelope


def parse_assigned_page(
    provider: str,
    payload: dict,
    *,
    connection_id: str,
    observed_at: str,
    owner_emails: dict[str, str] | None = None,
) -> dict:
    """owner_emails maps the CRM owner id to its email; both CRMs return only the id on contacts."""
    if provider not in {"hubspot", "pipedrive"}:
        raise ValueError(f"proveedor no soportado: {provider}")
    error_kind = payload.get("error_kind")
    if error_kind:
        return _error_envelope(str(error_kind), connection_id=connection_id, observed_at=observed_at)
    owners = owner_emails or {}
    if provider == "hubspot":
        return _hubspot(payload, owners, connection_id=connection_id, observed_at=observed_at)
    return _pipedrive(payload, owners, connection_id=connection_id, observed_at=observed_at)


def _hubspot(payload: dict, owners: dict[str, str], *, connection_id: str, observed_at: str) -> dict:
    """The cursor is the last contact id: search paging stops at 10,000 results, an id filter does not."""
    items = []
    for row in payload.get("results") or []:
        props = row.get("properties") or {}
        first = str(props.get("firstname") or "").strip()
        last = str(props.get("lastname") or "").strip()
        contact_name = " ".join(part for part in (first, last) if part).strip() or None
        last_contacted = props.get("notes_last_contacted") or None
        items.append({
            "contact_id": str(row["id"]),
            "deal_id": None,
            "contact_name": contact_name,
            "owner_email": owners.get(str(props.get("hubspot_owner_id") or "")),
            "last_call_at": last_contacted,
            "contacted": last_contacted is not None,
        })
    more = bool(((payload.get("paging") or {}).get("next") or {}).get("after"))
    cursor = items[-1]["contact_id"] if more and items else None
    envelope = read_envelope(
        items=items,
        coverage="partial" if cursor else "complete",
        observed_at=observed_at,
        connection_id=connection_id,
        object_type="contact",
        next_cursor=cursor,
    )
    envelope["connection_id"] = connection_id
    return envelope


def _pipedrive(payload: dict, owners: dict[str, str], *, connection_id: str, observed_at: str) -> dict:
    items = []
    for row in payload.get("data") or []:
        owner = row.get("owner_id")
        if isinstance(owner, dict):
            owner_email = owner.get("email")
        else:
            owner_email = owners.get(str(owner)) if owner is not None else None
        done = row.get("done_activities_count")
        contact_name = str(row.get("name") or "").strip() or None
        items.append({
            "contact_id": str(row["id"]),
            "deal_id": None,
            "contact_name": contact_name,
            "owner_email": owner_email,
            "last_call_at": None,
            "contacted": None if done is None else int(done) > 0,
        })
    extra = payload.get("additional_data") or {}
    pagination = extra.get("pagination") or {}
    if pagination.get("more_items_in_collection"):
        cursor = str(pagination["next_start"])
    elif extra.get("next_cursor"):
        cursor = str(extra["next_cursor"])
    else:
        cursor = None
    envelope = read_envelope(
        items=items,
        coverage="partial" if cursor else "complete",
        observed_at=observed_at,
        connection_id=connection_id,
        object_type="contact",
        next_cursor=cursor,
    )
    envelope["connection_id"] = connection_id
    return envelope


def _assigned_url(provider: str, request: dict, *, api_domain: str | None) -> str:
    path = request["path"]
    if not path.startswith("/"):
        path = f"/{path}"
    if provider == "hubspot":
        return f"{_HUBSPOT_BASE}{path}"
    if provider == "pipedrive":
        if not api_domain:
            raise ValueError("Pipedrive connection missing api_domain in metadata")
        version = request.get("version") or "v1"
        return f"{api_domain.rstrip('/')}/api/{version}{path}"
    raise ValueError(f"proveedor no soportado: {provider}")


def _expires_at(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


async def fresh_connection(supabase, connection: dict[str, Any]) -> dict[str, Any]:
    """HubSpot OAuth tokens last 30 minutes. A failed refresh keeps the old token, whose 401 reads as auth_expired."""
    provider = str(connection.get("provider") or "").strip().lower()
    try:
        if provider == "hubspot":
            from app.services.hubspot.oauth import ensure_fresh_hubspot_connection

            return await run_in_threadpool(ensure_fresh_hubspot_connection, supabase, connection)
        if provider == "pipedrive" and connection.get("refresh_token"):
            from app.services.pipedrive.client import PipedriveClient

            meta = connection.get("metadata") or {}
            client = PipedriveClient(
                str(meta.get("api_domain") or ""),
                str(connection.get("access_token") or ""),
                refresh_token=connection.get("refresh_token"),
                connection_id=str(connection.get("id") or "") or None,
                supabase=supabase,
                token_expires_at=_expires_at(connection.get("token_expires_at")),
            )
            await client.refresh_if_needed()
            return {**connection, "access_token": client.access_token}
    except Exception as exc:
        logger.warning("CRM token refresh failed for %s: %s", connection.get("id"), exc)
    return connection


def connection_assigned_fetch(
    connection: dict[str, Any],
    *,
    client: httpx.Client | None = None,
) -> Callable[[dict], dict]:
    """Build a fetch(request) that calls the CRM with the connection access_token."""
    provider = str(connection.get("provider") or "").strip().lower()
    if provider not in {"hubspot", "pipedrive"}:
        raise ValueError(f"proveedor no soportado: {provider}")
    token = str(connection.get("access_token") or "").strip()
    meta = connection.get("metadata") or {}
    api_domain = meta.get("api_domain") if isinstance(meta, dict) else None

    def _request(http: httpx.Client, request: dict) -> dict:
        url = _assigned_url(provider, request, api_domain=str(api_domain) if api_domain else None)
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        method = str(request.get("method") or "GET").upper()
        if method == "POST":
            headers["Content-Type"] = "application/json"
        for attempt in range(_RATE_LIMIT_RETRIES + 1):
            try:
                if method == "POST":
                    response = http.request(method, url, headers=headers, json=request.get("json"))
                else:
                    response = http.request(method, url, headers=headers, params=request.get("params"))
            except httpx.TimeoutException:
                return {"error_kind": "timeout"}
            except (httpx.ConnectError, httpx.NetworkError) as exc:
                raise TimeoutError(str(exc)) from exc
            if response.status_code != 429:
                break
            if attempt == _RATE_LIMIT_RETRIES:
                return {"error_kind": "rate_limited"}
            _sleep(_retry_after(response))
        if response.status_code in {401, 403}:
            return {"error_kind": str(response.status_code)}
        response.raise_for_status()
        body = response.json()
        return body if isinstance(body, dict) else {"data": body}

    def fetch(request: dict) -> dict:
        if not token:
            return {"error_kind": "unavailable"}
        if provider == "pipedrive" and not api_domain:
            return {"error_kind": "unavailable"}
        if client is not None:
            return _request(client, request)
        http = httpx.Client(timeout=_ASSIGNED_TIMEOUT)
        try:
            return _request(http, request)
        finally:
            http.close()

    return fetch


def _retry_after(response: httpx.Response) -> float:
    try:
        seconds = float(response.headers.get("Retry-After") or 1)
    except ValueError:
        seconds = 1.0
    return min(max(seconds, 0.0), _MAX_RETRY_WAIT)


def owners_request(provider: str, cursor: str | None) -> dict:
    if provider == "hubspot":
        params: dict[str, Any] = {"limit": 100}
        if cursor:
            params["after"] = cursor
        return {"method": "GET", "path": "/crm/v3/owners", "params": params}
    if provider == "pipedrive":
        return {"method": "GET", "path": "/users", "version": "v1"}
    raise ValueError(f"proveedor no soportado: {provider}")


def assigned_request(provider: str, cursor: str | None, owner_ids: list[str]) -> dict:
    """HubSpot takes every owner in one search; Pipedrive filters persons by a single owner_id."""
    if provider == "hubspot":
        filters: list[dict[str, Any]] = [
            {"propertyName": "hubspot_owner_id", "operator": "IN", "values": list(owner_ids)},
        ]
        if cursor:
            filters.append({"propertyName": "hs_object_id", "operator": "GT", "value": cursor})
        body: dict[str, Any] = {
            "limit": _HUBSPOT_PAGE,
            "properties": ["firstname", "lastname", "hubspot_owner_id", "notes_last_contacted"],
            "sorts": [{"propertyName": "hs_object_id", "direction": "ASCENDING"}],
            "filterGroups": [{"filters": filters}],
        }
        return {"method": "POST", "path": "/crm/v3/objects/contacts/search", "json": body}
    if provider == "pipedrive":
        params: dict[str, Any] = {
            "limit": _PIPEDRIVE_PAGE,
            "owner_id": owner_ids[0],
            "include_fields": "done_activities_count",
        }
        if cursor:
            params["cursor"] = cursor
        return {"method": "GET", "path": "/persons", "version": "v2", "params": params}
    raise ValueError(f"proveedor no soportado: {provider}")


class _ReadFailed(Exception):
    def __init__(self, envelope: dict):
        self.envelope = envelope


def _call(fetch, request: dict, *, connection_id: str, observed_at: str) -> dict:
    try:
        payload = fetch(request) or {}
    except (TimeoutError, OSError, httpx.HTTPError):
        raise _ReadFailed(_error_envelope("timeout", connection_id=connection_id, observed_at=observed_at))
    if payload.get("error_kind"):
        raise _ReadFailed(_error_envelope(str(payload["error_kind"]), connection_id=connection_id, observed_at=observed_at))
    return payload


def _owner_emails(provider: str, fetch, *, connection_id: str, observed_at: str, max_pages: int) -> dict[str, str]:
    owners: dict[str, str] = {}
    cursor = None
    for _ in range(max_pages):
        payload = _call(fetch, owners_request(provider, cursor), connection_id=connection_id, observed_at=observed_at)
        rows = payload.get("results") if provider == "hubspot" else payload.get("data")
        for owner in rows or []:
            email = str(owner.get("email") or "").strip().lower()
            if email and owner.get("id") is not None:
                owners[str(owner["id"])] = email
        cursor = ((payload.get("paging") or {}).get("next") or {}).get("after") if provider == "hubspot" else None
        if not cursor:
            break
    return owners


def collect_assigned(
    provider: str,
    fetch,
    *,
    connection_id: str,
    observed_at: str,
    member_emails: set[str],
    max_pages: int | None = None,
) -> dict:
    """Walk contacts owned by company members. A failed read returns no items, so the previous cache can stay."""
    max_pages = max_pages or _MAX_PAGES
    wanted_emails = {str(email).strip().lower() for email in member_emails if email}
    try:
        owners = _owner_emails(provider, fetch, connection_id=connection_id, observed_at=observed_at, max_pages=max_pages)
        owner_ids = sorted(oid for oid, email in owners.items() if email in wanted_emails)
        scopes = [owner_ids] if provider == "hubspot" else [[oid] for oid in owner_ids]
        items: list[dict] = []
        unfinished = None
        for scope in scopes if owner_ids else []:
            cursor = None
            for _ in range(max_pages):
                payload = _call(
                    fetch,
                    assigned_request(provider, cursor, scope),
                    connection_id=connection_id,
                    observed_at=observed_at,
                )
                page = parse_assigned_page(
                    provider,
                    payload,
                    connection_id=connection_id,
                    observed_at=observed_at,
                    owner_emails=owners,
                )
                items.extend(page.get("items") or [])
                cursor = page.get("next_cursor")
                if not cursor:
                    break
            unfinished = unfinished or cursor
    except _ReadFailed as failed:
        return failed.envelope
    envelope = read_envelope(
        items=items,
        coverage="partial" if unfinished else "complete",
        observed_at=observed_at,
        connection_id=connection_id,
        object_type="contact",
        next_cursor=unfinished,
    )
    envelope["connection_id"] = connection_id
    return envelope
