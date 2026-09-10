"""Persist Stripe state on company_billing. Idempotent webhook event log."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from supabase import Client

from app.services.billing.entitlement import (
    billing_row_from_subscription,
    company_id_from_stripe_object,
    should_sync_seat_limit,
    stripe_obj_get,
    subscription_quantity,
)

logger = logging.getLogger(__name__)


def _missing_billing_schema(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "company_billing" in msg and (
        "could not find" in msg or "does not exist" in msg or "pgrst205" in msg
    )


def claim_event(supabase: Client, event_id: str, event_type: str) -> bool:
    """Return True if this event should be treated as newly recorded."""
    existing = (
        supabase.table("stripe_webhook_events")
        .select("id")
        .eq("id", event_id)
        .limit(1)
        .execute()
    )
    if existing.data:
        return False
    try:
        supabase.table("stripe_webhook_events").insert(
            {"id": event_id, "event_type": event_type}
        ).execute()
    except Exception as exc:
        logger.info("stripe event %s already claimed: %s", event_id, exc)
        return False
    return True


def get_billing(supabase: Client, company_id: str) -> Optional[dict]:
    try:
        result = (
            supabase.table("company_billing")
            .select("*")
            .eq("company_id", company_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        if _missing_billing_schema(exc):
            return None
        raise
    rows = result.data or []
    return rows[0] if rows else None


def company_by_id(supabase: Client, company_id: str) -> Optional[dict]:
    result = (
        supabase.table("companies").select("*").eq("id", company_id).limit(1).execute()
    )
    rows = result.data or []
    return rows[0] if rows else None


def company_by_customer(supabase: Client, customer_id: str) -> Optional[dict]:
    try:
        result = (
            supabase.table("company_billing")
            .select("company_id")
            .eq("stripe_customer_id", customer_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        if _missing_billing_schema(exc):
            return None
        raise
    rows = result.data or []
    if not rows:
        return None
    return company_by_id(supabase, str(rows[0]["company_id"]))


def resolve_company(supabase: Client, obj: Any) -> Optional[dict]:
    cid = company_id_from_stripe_object(obj)
    if cid:
        company = company_by_id(supabase, cid)
        if company:
            return company
    customer = stripe_obj_get(obj, "customer")
    customer_id = customer if isinstance(customer, str) else stripe_obj_get(customer, "id")
    if customer_id:
        return company_by_customer(supabase, str(customer_id))
    return None


def upsert_customer(supabase: Client, company_id: str, customer_id: str) -> dict:
    existing = get_billing(supabase, company_id) or {}
    row = {
        "company_id": company_id,
        "stripe_customer_id": customer_id,
        "billing_status": existing.get("billing_status") or "none",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if not existing:
        row["created_at"] = row["updated_at"]
    result = (
        supabase.table("company_billing")
        .upsert(row, on_conflict="company_id")
        .execute()
    )
    rows = result.data or []
    return rows[0] if rows else {**existing, **row}


def upsert_billing(supabase: Client, company_id: str, patch: dict) -> dict:
    row = {
        "company_id": company_id,
        **{k: v for k, v in patch.items() if k != "company_id"},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    result = (
        supabase.table("company_billing")
        .upsert(row, on_conflict="company_id")
        .execute()
    )
    rows = result.data or []
    return rows[0] if rows else row


def apply_subscription(
    supabase: Client,
    company: dict,
    subscription: Any,
    *,
    deleted: bool = False,
) -> dict:
    company_id = str(company["id"])
    existing = get_billing(supabase, company_id)
    billing = billing_row_from_subscription(
        subscription, deleted=deleted, existing=existing
    )
    saved = upsert_billing(supabase, company_id, billing)
    if should_sync_seat_limit(company, billing, deleted=deleted):
        supabase.table("companies").update(
            {"seat_limit": subscription_quantity(subscription)}
        ).eq("id", company_id).execute()
    return saved
