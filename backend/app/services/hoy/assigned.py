"""Turn one HubSpot or Pipedrive assigned-contacts page into a read envelope."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from app.services.crm_providers.coverage import from_provider_error, read_envelope

_HUBSPOT_BASE = "https://api.hubapi.com"
_ASSIGNED_TIMEOUT = 30.0


def parse_assigned_page(provider: str, payload: dict, *, connection_id: str, observed_at: str) -> dict:
    if provider not in {"hubspot", "pipedrive"}:
        raise ValueError(f"proveedor no soportado: {provider}")
    error_kind = payload.get("error_kind")
    if error_kind:
        kind = str(error_kind)
        if kind in {"401", "403"}:
            kind = "email_scope_missing"
        envelope = from_provider_error(
            kind,
            observed_at=observed_at,
            connection_id=connection_id,
            object_type="contact",
        )
        envelope["connection_id"] = connection_id
        return envelope
    if provider == "hubspot":
        return _hubspot(payload, connection_id=connection_id, observed_at=observed_at)
    return _pipedrive(payload, connection_id=connection_id, observed_at=observed_at)


def _hubspot(payload: dict, *, connection_id: str, observed_at: str) -> dict:
    items = []
    for row in payload.get("results") or []:
        props = row.get("properties") or {}
        first = str(props.get("firstname") or "").strip()
        last = str(props.get("lastname") or "").strip()
        contact_name = " ".join(part for part in (first, last) if part).strip() or None
        items.append({
            "contact_id": str(row["id"]),
            "deal_id": props.get("deal_id") or None,
            "contact_name": contact_name,
            "owner_email": props.get("owner_email"),
            "owner_name": props.get("owner_name"),
            "last_call_at": props.get("last_call_at"),
        })
    cursor = ((payload.get("paging") or {}).get("next") or {}).get("after")
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


def _pipedrive(payload: dict, *, connection_id: str, observed_at: str) -> dict:
    items = []
    for row in payload.get("data") or []:
        owner = row.get("owner_id") or {}
        if isinstance(owner, dict):
            owner_email = owner.get("email")
            owner_name = owner.get("name")
        else:
            owner_email = None
            owner_name = None
        contact_name = str(row.get("name") or "").strip() or None
        items.append({
            "contact_id": str(row["id"]),
            "deal_id": str(row["deal_id"]) if row.get("deal_id") else None,
            "contact_name": contact_name,
            "owner_email": owner_email,
            "owner_name": owner_name,
            "last_call_at": row.get("last_activity_date"),
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
        try:
            if method == "POST":
                headers["Content-Type"] = "application/json"
                response = http.request(method, url, headers=headers, json=request.get("json"))
            else:
                response = http.request(method, url, headers=headers, params=request.get("params"))
        except httpx.TimeoutException:
            return {"error_kind": "timeout"}
        except (httpx.ConnectError, httpx.NetworkError) as exc:
            raise TimeoutError(str(exc)) from exc
        if response.status_code in {401, 403}:
            return {"error_kind": "403"}
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


def assigned_request(provider: str, cursor: str | None) -> dict:
    if provider == "hubspot":
        body = {
            "limit": 100,
            "properties": ["email", "firstname", "lastname", "hubspot_owner_id", "notes_last_contacted"],
        }
        if cursor:
            body["after"] = cursor
        return {"method": "POST", "path": "/crm/v3/objects/contacts/search", "json": body}
    if provider == "pipedrive":
        params = {"limit": 100}
        if cursor:
            params["cursor"] = cursor
        return {"method": "GET", "path": "/persons", "version": "v2", "params": params}
    raise ValueError(f"proveedor no soportado: {provider}")


def collect_assigned(provider: str, fetch, *, connection_id: str, observed_at: str, max_pages: int = 5) -> dict:
    """Walk assigned-contact pages. A transport failure returns no items, so the previous cache can stay."""
    items: list[dict] = []
    cursor = None
    for _ in range(max_pages):
        try:
            payload = fetch(assigned_request(provider, cursor))
        except (TimeoutError, OSError):
            envelope = from_provider_error(
                "timeout",
                observed_at=observed_at,
                connection_id=connection_id,
                object_type="contact",
            )
            envelope["connection_id"] = connection_id
            return envelope
        page = parse_assigned_page(provider, payload or {}, connection_id=connection_id, observed_at=observed_at)
        if page.get("coverage") in {"forbidden", "unavailable"} and not page.get("items"):
            return page
        items.extend(page.get("items") or [])
        cursor = page.get("next_cursor")
        if not cursor:
            break
    envelope = read_envelope(
        items=items,
        coverage="complete" if not cursor else "partial",
        observed_at=observed_at,
        connection_id=connection_id,
        object_type="contact",
        next_cursor=cursor,
    )
    envelope["connection_id"] = connection_id
    return envelope
