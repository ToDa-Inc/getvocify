"""Map MemoExtraction nested bags to Pipedrive person/org/deal property dicts."""

from __future__ import annotations

from typing import Any, Optional

from app.models.memo import MemoExtraction


def _nonempty_props(props: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in props.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        out[key] = value
    return out


def deal_properties_from_extraction(
    extraction: MemoExtraction,
    mapped: dict[str, Any],
    allowed_fields: Optional[list[str]] = None,
) -> dict[str, Any]:
    raw = extraction.raw_extraction or {}
    props = dict(mapped)
    for key, value in raw.items():
        if key in {"contact_properties", "company_properties", "line_items", "confidence", "summary", "nextSteps"}:
            continue
        if value is not None and value != "":
            props[key] = value
    props = _nonempty_props(props)
    if allowed_fields is not None:
        allow = set(allowed_fields)
        props = {k: v for k, v in props.items() if k in allow}
    return props


def contact_properties_from_extraction(
    extraction: MemoExtraction,
    allowed_fields: Optional[list[str]] = None,
    identity_props: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
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
