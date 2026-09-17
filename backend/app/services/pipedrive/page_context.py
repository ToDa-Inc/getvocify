"""Map Pipedrive records to the extension page-context DTO (HubSpot-shaped)."""

from __future__ import annotations

from typing import Any, Optional

from .search import primary_email, primary_phone


def assoc_id(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, dict):
        value = value.get("id") if value.get("id") is not None else value.get("value")
    if value is None or value == "":
        return None
    return str(value)


def person_names(person: dict[str, Any]) -> tuple[str, str, Optional[str]]:
    first = str(person.get("first_name") or "").strip()
    last = str(person.get("last_name") or "").strip()
    name = str(person.get("name") or "").strip()
    if not first and name:
        parts = name.split(None, 1)
        first = parts[0]
        last = parts[1] if len(parts) > 1 else ""
    display = name or f"{first} {last}".strip() or None
    return first, last, display


def contact_from_person(
    person: dict[str, Any],
    *,
    company_id: Optional[str] = None,
    company_name: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    pid = assoc_id(person.get("id"))
    if not pid:
        return None
    _first, _last, name = person_names(person)
    org = person.get("org_id")
    org_name = org.get("name") if isinstance(org, dict) else person.get("org_name")
    return {
        "contact_id": pid,
        "name": name,
        "email": primary_email(person) or None,
        "phone": primary_phone(person),
        "company_id": company_id or assoc_id(org),
        "company_name": company_name or org_name,
    }


def deal_raw_extraction(deal: dict[str, Any]) -> dict[str, Any]:
    amount = deal.get("value")
    if isinstance(amount, dict):
        amount = amount.get("value") if amount.get("value") is not None else amount.get("amount")
    try:
        amount_f = float(amount) if amount is not None and amount != "" else None
    except (TypeError, ValueError):
        amount_f = None
    stage = deal.get("stage_id")
    return {
        "dealname": deal.get("title"),
        "amount": amount_f,
        "closedate": deal.get("expected_close_date") or deal.get("close_time"),
        "dealstage": str(stage) if stage is not None else None,
    }
