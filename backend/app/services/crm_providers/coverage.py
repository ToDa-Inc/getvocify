"""CRM read envelope. An empty list is absence only when coverage is complete."""

from __future__ import annotations

from typing import Any, Optional


def read_envelope(
    *,
    items: list[dict],
    coverage: str,
    observed_at: str,
    connection_id: str,
    object_type: str,
    next_cursor: Optional[str] = None,
    reason: Optional[str] = None,
) -> dict[str, Any]:
    if coverage not in {"complete", "partial", "forbidden", "unavailable"}:
        raise ValueError(f"cobertura desconocida: {coverage}")
    tagged = []
    for item in items:
        tagged.append({
            **item,
            "connection_id": connection_id,
            "object_type": item.get("object_type") or object_type,
        })
    return {
        "items": tagged,
        "coverage": coverage,
        "observed_at": observed_at,
        "next_cursor": next_cursor,
        "reason": reason,
    }


def from_provider_error(
    kind: str,
    *,
    observed_at: str,
    connection_id: str,
    object_type: str,
) -> dict[str, Any]:
    if kind == "email_scope_missing":
        coverage, reason = "forbidden", "email_scope_missing"
    elif kind in {"timeout", "transport"}:
        coverage, reason = "unavailable", "provider_unavailable"
    else:
        coverage, reason = "unavailable", kind or "provider_unavailable"
    return read_envelope(
        items=[],
        coverage=coverage,
        observed_at=observed_at,
        connection_id=connection_id,
        object_type=object_type,
        reason=reason,
    )


def means_no_activity(envelope: dict) -> bool:
    return envelope.get("coverage") == "complete" and envelope.get("items") == []


def deny_foreign(requested_connection_id: str, resource_connection_id: str) -> None:
    if requested_connection_id != resource_connection_id:
        raise PermissionError("objeto de otra conexión")
