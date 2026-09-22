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
        items.append({
            "contact_id": str(row["id"]),
            "deal_id": str(row["deal_id"]) if row.get("deal_id") else None,
            "owner_email": owner.get("email") if isinstance(owner, dict) else None,
            "owner_name": owner.get("name") if isinstance(owner, dict) else None,
            "last_call_at": row.get("last_activity_date"),
        })
    pagination = ((payload.get("additional_data") or {}).get("pagination") or {})
    cursor = str(pagination["next_start"]) if pagination.get("more_items_in_collection") else None
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
