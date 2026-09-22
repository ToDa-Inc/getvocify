"""Turn one HubSpot or Pipedrive assigned-contacts page into a read envelope."""

from __future__ import annotations

from app.services.crm_providers.coverage import from_provider_error, read_envelope


def parse_assigned_page(provider: str, payload: dict, *, connection_id: str, observed_at: str) -> dict:
    if provider not in {"hubspot", "pipedrive"}:
        raise ValueError(f"proveedor no soportado: {provider}")
    error_kind = payload.get("error_kind")
    if error_kind:
        envelope = from_provider_error(
            str(error_kind),
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
        items.append({
            "contact_id": str(row["id"]),
            "deal_id": props.get("deal_id") or None,
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
        items.append({
            "contact_id": str(row["id"]),
            "deal_id": str(row["deal_id"]) if row.get("deal_id") else None,
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


def assigned_request(provider: str, cursor: str | None) -> dict:
    if provider == "hubspot":
        body = {"limit": 100, "properties": ["email", "hubspot_owner_id", "notes_last_contacted"]}
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
