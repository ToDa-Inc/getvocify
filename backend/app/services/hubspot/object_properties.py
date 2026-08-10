"""
Helpers for mapping MemoExtraction → HubSpot object property bags by allowlist.
"""

from __future__ import annotations

from typing import Any, Optional

from app.models.memo import MemoExtraction


CONTACT_IDENTITY_KEYS = frozenset({"email", "firstname", "lastname", "phone", "jobtitle"})
COMPANY_IDENTITY_KEYS = frozenset({"name", "domain"})


def _nonempty_props(props: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in props.items():
        if v is None:
            continue
        if isinstance(v, str) and not v.strip():
            continue
        out[k] = v
    return out


def contact_properties_from_extraction(
    extraction: MemoExtraction,
    allowed_fields: Optional[list[str]] = None,
    identity_props: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Build HubSpot contact properties from identity mapping + nested contact_properties.
    Filtered by allowed_fields when provided.
    """
    raw = extraction.raw_extraction or {}
    nested = raw.get("contact_properties") if isinstance(raw.get("contact_properties"), dict) else {}
    props: dict[str, Any] = {}
    if identity_props:
        props.update(identity_props)
    props.update(nested)
    props = _nonempty_props(props)
    if allowed_fields is not None:
        allow = set(allowed_fields)
        props = {k: v for k, v in props.items() if k in allow}
    return props


def company_properties_from_extraction(
    extraction: MemoExtraction,
    allowed_fields: Optional[list[str]] = None,
    identity_props: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Build HubSpot company properties from identity mapping + nested company_properties."""
    raw = extraction.raw_extraction or {}
    nested = raw.get("company_properties") if isinstance(raw.get("company_properties"), dict) else {}
    props: dict[str, Any] = {}
    if identity_props:
        props.update(identity_props)
    props.update(nested)
    props = _nonempty_props(props)
    if allowed_fields is not None:
        allow = set(allowed_fields)
        props = {k: v for k, v in props.items() if k in allow}
    return props


def line_items_from_extraction(
    extraction: MemoExtraction,
    allowed_fields: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    """Return list of line-item property dicts filtered by allowlist."""
    raw = extraction.raw_extraction or {}
    items = raw.get("line_items")
    if not isinstance(items, list):
        return []
    allow = set(allowed_fields) if allowed_fields is not None else None
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        props = _nonempty_props(item)
        if allow is not None:
            props = {k: v for k, v in props.items() if k in allow}
        if props.get("name") or props.get("hs_product_id"):
            out.append(props)
    return out
