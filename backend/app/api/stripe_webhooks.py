"""Signed Stripe webhooks for seat subscriptions."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from supabase import Client

from app.deps import get_supabase
from app.services.billing.entitlement import stripe_obj_get
from app.services.billing.store import apply_subscription, claim_event, resolve_company
from app.services.billing.stripe_service import StripeService, StripeServiceError

logger = logging.getLogger(__name__)
router = APIRouter(tags=["stripe_webhooks"])

HANDLED = frozenset(
    {
        "checkout.session.completed",
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
        "invoice.payment_succeeded",
        "invoice.payment_failed",
    }
)


def _subscription_id(obj: Any, event_type: str) -> str | None:
    if event_type.startswith("customer.subscription."):
        return stripe_obj_get(obj, "id")
    if event_type.startswith("invoice."):
        sub = stripe_obj_get(obj, "subscription")
        return sub if isinstance(sub, str) else stripe_obj_get(sub, "id")
    if event_type.startswith("checkout.session."):
        sub = stripe_obj_get(obj, "subscription")
        return sub if isinstance(sub, str) else stripe_obj_get(sub, "id")
    return None


def _apply_event(supabase: Client, event_type: str, obj: Any, stripe_svc: StripeService) -> None:
    if event_type.startswith("customer.subscription."):
        company = resolve_company(supabase, obj)
        if not company:
            return
        apply_subscription(
            supabase,
            company,
            obj,
            deleted=event_type.endswith(".deleted"),
        )
        return
    sub_id = _subscription_id(obj, event_type)
    if not sub_id:
        return
    subscription = stripe_svc.retrieve_subscription(str(sub_id))
    company = resolve_company(supabase, subscription) or resolve_company(supabase, obj)
    if company:
        apply_subscription(supabase, company, subscription)


@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    supabase: Client = Depends(get_supabase),
):
    payload = await request.body()
    signature = request.headers.get("stripe-signature")
    if not signature:
        return JSONResponse(status_code=400, content={"error": "Missing Stripe signature"})
    try:
        stripe_svc = StripeService()
        event = stripe_svc.verify_webhook(payload, signature)
    except StripeServiceError as exc:
        logger.warning("stripe webhook verify failed: %s", exc)
        return JSONResponse(status_code=400, content={"error": "Invalid webhook signature"})

    event_type = str(stripe_obj_get(event, "type") or "unknown")
    event_id = str(stripe_obj_get(event, "id") or "")
    if not event_id:
        return JSONResponse(status_code=400, content={"error": "Missing event id"})

    if event_type not in HANDLED:
        return JSONResponse(status_code=200, content={"received": True, "ignored": event_type})

    existing = (
        supabase.table("stripe_webhook_events")
        .select("id")
        .eq("id", event_id)
        .limit(1)
        .execute()
    )
    if existing.data:
        return JSONResponse(status_code=200, content={"received": True, "duplicate": True})

    data = stripe_obj_get(event, "data") or {}
    obj = stripe_obj_get(data, "object")
    try:
        _apply_event(supabase, event_type, obj, stripe_svc)
    except Exception:
        logger.exception("stripe webhook handler failed event=%s type=%s", event_id, event_type)
        return JSONResponse(status_code=500, content={"error": "Webhook apply failed"})

    claim_event(supabase, event_id, event_type)
    return JSONResponse(status_code=200, content={"received": True, "event_type": event_type})
