"""Load seller offer context and current CRM values for extraction prompts."""

from __future__ import annotations

import logging
from typing import Any, Optional

from supabase import Client

from app.logging_config import DOMAIN_EXTRACTION, log_domain

logger = logging.getLogger(__name__)

_CONTACT_IDENTITY = ("firstname", "lastname", "email")
_HS_OBJECT_PATH = {
    "contacts": "contacts",
    "companies": "companies",
    "deals": "deals",
}


def load_product_context(supabase: Client, user_id: str) -> str:
    try:
        result = (
            supabase.table("user_profiles")
            .select("product_context")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        if not rows:
            return ""
        return str(rows[0].get("product_context") or "").strip()
    except Exception as e:
        logger.warning(
            "Could not load product_context",
            extra=log_domain(DOMAIN_EXTRACTION, "product_context_load_failed", error=str(e)),
        )
        return ""


def _spec_names_by_object(field_specs: Optional[list[dict]]) -> dict[str, list[str]]:
    names: dict[str, list[str]] = {"contacts": [], "companies": [], "deals": []}
    for spec in field_specs or []:
        obj = spec.get("object_type") or "deals"
        name = spec.get("name")
        if name and obj in names and name not in names[obj]:
            names[obj].append(name)
    for ident in _CONTACT_IDENTITY:
        if ident not in names["contacts"]:
            names["contacts"].append(ident)
    return names


async def _hubspot_properties(
    client: Any,
    object_type: str,
    object_id: Optional[str],
    property_names: list[str],
) -> dict[str, Any]:
    if not object_id or not property_names:
        return {}
    path = _HS_OBJECT_PATH.get(object_type)
    if not path:
        return {}
    try:
        resp = await client.get(
            f"/crm/v3/objects/{path}/{object_id}",
            params={"properties": ",".join(property_names)},
        )
        props = (resp or {}).get("properties") or {}
        return {k: v for k, v in props.items() if v not in (None, "")}
    except Exception as e:
        logger.warning(
            "Could not load existing %s properties",
            object_type,
            extra=log_domain(
                DOMAIN_EXTRACTION,
                "existing_crm_load_failed",
                object_type=object_type,
                error=str(e),
            ),
        )
        return {}


async def load_existing_crm_values(
    supabase: Client,
    user_id: str,
    memo_data: Optional[dict],
    field_specs: Optional[list[dict]] = None,
) -> dict[str, dict[str, Any]]:
    """Best-effort snapshot of the CRM record this memo will update."""
    if not memo_data:
        return {}
    try:
        from app.services.memo_crm import get_memo_crm_or_none_with_hubspot_refresh
        from app.services.hubspot.client import HubSpotClient

        _provider, conn = await get_memo_crm_or_none_with_hubspot_refresh(supabase, user_id)
    except Exception:
        return {}
    if not conn or conn.get("provider") != "hubspot":
        return {}

    names = _spec_names_by_object(field_specs)
    contact_id = memo_data.get("hubspot_contact_id")
    deal_id = memo_data.get("hubspot_deal_id") or memo_data.get("matched_deal_id")
    if not contact_id and not deal_id:
        return {}

    client = HubSpotClient(conn["access_token"])
    existing: dict[str, dict[str, Any]] = {}
    contact_props = await _hubspot_properties(client, "contacts", contact_id, names["contacts"])
    if contact_props:
        existing["contacts"] = contact_props
    deal_props = await _hubspot_properties(client, "deals", deal_id, names["deals"])
    if deal_props:
        existing["deals"] = deal_props
    return existing


async def load_extraction_llm_context(
    supabase: Client,
    user_id: str,
    *,
    memo_id: Optional[str] = None,
    memo_data: Optional[dict] = None,
    field_specs: Optional[list[dict]] = None,
) -> tuple[str, dict[str, dict[str, Any]]]:
    product_context = load_product_context(supabase, user_id)
    data = memo_data
    if data is None and memo_id:
        try:
            result = (
                supabase.table("memos")
                .select("hubspot_deal_id,hubspot_contact_id,matched_deal_id")
                .eq("id", memo_id)
                .limit(1)
                .execute()
            )
            rows = result.data or []
            data = rows[0] if rows else None
        except Exception:
            data = None
    existing = await load_existing_crm_values(supabase, user_id, data, field_specs)
    return product_context, existing
