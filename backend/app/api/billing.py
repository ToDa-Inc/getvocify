"""Company workspace billing: checkout, portal, status."""

from __future__ import annotations

import logging
from typing import Literal, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from supabase import Client

from app.config import settings
from app.deps import get_supabase, get_user_id
from app.services.billing.catalog import catalog_payload
from app.services.billing.entitlement import (
    billing_status_of,
    plan_type_of,
    subscription_item_id,
    workspace_entitlements,
)
from app.services.billing.store import upsert_customer
from app.services.billing.stripe_service import (
    StripeService,
    StripeServiceError,
    stripe_configured,
)
from app.services.company import CompanyService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/billing", tags=["billing"])

LIVE_STATUSES = frozenset({"active", "trialing", "past_due", "incomplete"})


class PlanCard(BaseModel):
    id: Literal["starter", "pro"]
    name: str
    tagline: str
    monthly_amount: int
    yearly_amount: int
    yearly_monthly_amount: int
    yearly_discount_percent: int
    features: list[str]
    includes_dialer: bool = False
    dialer_minutes: Optional[int] = None


class BillingStatusResponse(BaseModel):
    configured: bool
    publishable_key: Optional[str] = None
    access_mode: str
    billing_status: str
    plan_type: Optional[str] = None
    billing_interval: Optional[str] = None
    current_period_end: Optional[str] = None
    cancel_at_period_end: bool = False
    seat_limit: int
    seats_used: int
    paywalled: bool
    can_manage: bool
    can_use_dialer: bool
    has_subscription: bool
    currency: str = "eur"
    yearly_discount_percent: int = 0
    plans: list[PlanCard] = Field(default_factory=list)


class CheckoutRequest(BaseModel):
    plan: Literal["starter", "pro"]
    interval: Literal["monthly", "yearly"]
    return_url: str


class CheckoutResponse(BaseModel):
    action: Literal["checkout", "updated"]
    checkout_url: Optional[str] = None
    client_secret: Optional[str] = None
    plan_type: Optional[str] = None


class PortalRequest(BaseModel):
    return_url: str


class PortalResponse(BaseModel):
    portal_url: str


def _require_manage(user_id: str, supabase: Client):
    return CompanyService(supabase).require_manage_role(user_id)


def _safe_return_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(status_code=400, detail="Invalid return_url")
    allowed = {
        urlparse(settings.FRONTEND_URL).netloc,
        "localhost:5173",
        "localhost:8080",
        "localhost:8081",
        "app.getvocify.com",
        "getvocify.com",
        "www.getvocify.com",
    }
    if parsed.netloc not in allowed:
        raise HTTPException(status_code=400, detail="return_url host is not allowed")
    return url


def _with_query(url: str, key: str, value: str) -> str:
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}{key}={value}"


def _user_email(supabase: Client, user_id: str) -> str:
    try:
        user = supabase.auth.admin.get_user_by_id(user_id)
        email = getattr(getattr(user, "user", user), "email", None)
        if email:
            return str(email)
    except Exception as exc:
        logger.warning("billing email lookup failed for %s: %s", user_id, exc)
    raise HTTPException(status_code=400, detail="Could not resolve account email")


def _status_payload(company: dict, billing: dict, usage: dict, role: str) -> BillingStatusResponse:
    entitlements = workspace_entitlements(company, billing)
    catalog = catalog_payload()
    return BillingStatusResponse(
        configured=stripe_configured(),
        publishable_key=settings.STRIPE_PUBLISHABLE_KEY or None,
        access_mode=entitlements["access_mode"],
        billing_status=entitlements["billing_status"],
        plan_type=entitlements["plan_type"],
        billing_interval=billing.get("billing_interval"),
        current_period_end=billing.get("current_period_end"),
        cancel_at_period_end=bool(billing.get("cancel_at_period_end")),
        seat_limit=usage["seat_limit"],
        seats_used=usage["seats_used"],
        paywalled=entitlements["paywalled"],
        can_manage=role in ("owner", "admin"),
        can_use_dialer=entitlements["can_use_dialer"],
        has_subscription=bool(billing.get("stripe_subscription_id")),
        currency=catalog["currency"],
        yearly_discount_percent=int(catalog.get("yearly_discount_percent") or 0),
        plans=[PlanCard(**plan) for plan in catalog["plans"]],
    )


@router.get("/status", response_model=BillingStatusResponse)
async def billing_status(
    user_id: str = Depends(get_user_id),
    supabase: Client = Depends(get_supabase),
):
    svc = CompanyService(supabase)
    membership = svc.require_membership(user_id)
    company = svc.get_company(membership.company_id)
    usage = svc.seat_usage(membership.company_id)
    billing = svc.billing_for(membership.company_id)
    return _status_payload(company, billing, usage, membership.role)


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(
    body: CheckoutRequest,
    user_id: str = Depends(get_user_id),
    supabase: Client = Depends(get_supabase),
):
    if not stripe_configured():
        raise HTTPException(status_code=503, detail="Billing is not configured")
    membership = _require_manage(user_id, supabase)
    svc = CompanyService(supabase)
    company = svc.get_company(membership.company_id)
    return_url = _safe_return_url(body.return_url)
    try:
        stripe_svc = StripeService()
        price_id = stripe_svc.price_id_for(body.plan, body.interval)
    except StripeServiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    billing = svc.billing_for(membership.company_id)
    customer_id = billing.get("stripe_customer_id")
    if not customer_id:
        customer_id = stripe_svc.create_customer(
            company_id=membership.company_id,
            email=_user_email(supabase, user_id),
            name=company.get("name"),
        )
        upsert_customer(supabase, membership.company_id, customer_id)

    sub_id = billing.get("stripe_subscription_id")
    status = billing_status_of(billing)
    if sub_id and status in LIVE_STATUSES:
        if plan_type_of(billing) == body.plan and billing.get("billing_interval") == body.interval:
            return CheckoutResponse(action="updated", plan_type=body.plan)
        try:
            subscription = stripe_svc.retrieve_subscription(str(sub_id))
            item_id = subscription_item_id(subscription)
            if not item_id:
                raise StripeServiceError("Subscription has no items")
            portal_url = stripe_svc.create_subscription_update_portal_session(
                customer_id=str(customer_id),
                return_url=_with_query(return_url, "billing", "success"),
                subscription_id=str(sub_id),
                subscription_item_id=str(item_id),
                price_id=price_id,
            )
        except StripeServiceError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return CheckoutResponse(
            action="checkout",
            checkout_url=portal_url,
            plan_type=body.plan,
        )

    try:
        session = stripe_svc.create_checkout_session(
            customer_id=str(customer_id),
            company_id=membership.company_id,
            plan=body.plan,
            interval=body.interval,
            price_id=price_id,
            return_url=_with_query(
                _with_query(return_url, "billing", "success"),
                "session_id",
                "{CHECKOUT_SESSION_ID}",
            ),
            success_url=_with_query(return_url, "billing", "success"),
            cancel_url=_with_query(return_url, "billing", "cancel"),
        )
    except StripeServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CheckoutResponse(
        action="checkout",
        checkout_url=session.get("checkout_url"),
        client_secret=session.get("client_secret"),
        plan_type=body.plan,
    )


@router.post("/portal", response_model=PortalResponse)
async def create_portal(
    body: PortalRequest,
    user_id: str = Depends(get_user_id),
    supabase: Client = Depends(get_supabase),
):
    if not stripe_configured():
        raise HTTPException(status_code=503, detail="Billing is not configured")
    membership = _require_manage(user_id, supabase)
    billing = CompanyService(supabase).billing_for(membership.company_id)
    customer_id = billing.get("stripe_customer_id")
    if not customer_id:
        raise HTTPException(status_code=400, detail="No billing customer yet")
    try:
        url = StripeService().create_portal_session(
            customer_id=str(customer_id),
            return_url=_safe_return_url(body.return_url),
        )
    except StripeServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PortalResponse(portal_url=url)
