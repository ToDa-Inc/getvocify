"""Thin Stripe customer / checkout / portal / subscription helper."""

from __future__ import annotations

import logging
from typing import Any, Optional

import stripe

from app.config import settings
from app.services.billing.catalog import product_id_for
from app.services.billing.entitlement import stripe_obj_get, subscription_item_id

logger = logging.getLogger(__name__)

_PRICE_CACHE: dict[tuple[str, str], str] = {}


class StripeServiceError(Exception):
    pass


def stripe_configured() -> bool:
    return bool(settings.STRIPE_SECRET_KEY)


def _price_override(plan: str, interval: str) -> Optional[str]:
    key = f"STRIPE_PRICE_{plan.upper()}_{interval.upper()}"
    value = getattr(settings, key, None)
    return str(value) if value else None


class StripeService:
    def __init__(self) -> None:
        if not settings.STRIPE_SECRET_KEY:
            raise StripeServiceError("STRIPE_SECRET_KEY is not set")
        stripe.api_key = settings.STRIPE_SECRET_KEY

    def price_id_for(self, plan: str, interval: str) -> str:
        override = _price_override(plan, interval)
        if override:
            return override
        cached = _PRICE_CACHE.get((plan, interval))
        if cached:
            return cached
        try:
            price_id = self._resolve_product_price(product_id_for(plan, interval), interval)
        except stripe.StripeError as exc:
            raise StripeServiceError(str(exc)) from exc
        _PRICE_CACHE[(plan, interval)] = price_id
        return price_id

    def _resolve_product_price(self, product_id: str, interval: str) -> str:
        stripe_interval = "year" if interval == "yearly" else "month"
        product = stripe.Product.retrieve(product_id)
        default = stripe_obj_get(product, "default_price")
        default_id = default if isinstance(default, str) else stripe_obj_get(default, "id")
        if default_id:
            price = stripe.Price.retrieve(str(default_id))
            recurring = stripe_obj_get(price, "recurring") or {}
            if stripe_obj_get(recurring, "interval") == stripe_interval:
                return str(default_id)
        prices = stripe.Price.list(product=product_id, active=True, limit=10)
        for price in getattr(prices, "data", None) or []:
            recurring = stripe_obj_get(price, "recurring") or {}
            if stripe_obj_get(recurring, "interval") == stripe_interval:
                pid = stripe_obj_get(price, "id")
                if pid:
                    return str(pid)
        raise StripeServiceError(f"No active {interval} price on {product_id}")

    def create_customer(
        self,
        *,
        company_id: str,
        email: str,
        name: Optional[str] = None,
    ) -> str:
        customer = stripe.Customer.create(
            email=email,
            name=name or None,
            metadata={"company_id": company_id},
        )
        cid = stripe_obj_get(customer, "id")
        if not cid:
            raise StripeServiceError("Stripe customer create returned no id")
        return str(cid)

    def create_checkout_session(
        self,
        *,
        customer_id: str,
        company_id: str,
        plan: str,
        interval: str,
        price_id: str,
        return_url: str,
        success_url: str,
        cancel_url: str,
    ) -> dict:
        meta = {"company_id": company_id, "plan_type": plan, "interval": interval}
        shared = {
            "mode": "subscription",
            "customer": customer_id,
            "client_reference_id": company_id,
            "line_items": [{"price": price_id, "quantity": 1}],
            "metadata": meta,
            "subscription_data": {"metadata": meta},
            "allow_promotion_codes": True,
        }
        for ui_mode in ("embedded_page", "embedded"):
            try:
                session = stripe.checkout.Session.create(
                    ui_mode=ui_mode,
                    return_url=return_url,
                    **shared,
                )
            except stripe.StripeError as exc:
                logger.info("embedded checkout ui_mode=%s rejected: %s", ui_mode, exc)
                continue
            secret = stripe_obj_get(session, "client_secret")
            if secret:
                return {"client_secret": str(secret), "checkout_url": None}
        session = stripe.checkout.Session.create(
            success_url=success_url,
            cancel_url=cancel_url,
            **shared,
        )
        url = stripe_obj_get(session, "url")
        if not url:
            raise StripeServiceError("Checkout session has no url")
        return {"client_secret": None, "checkout_url": str(url)}

    def create_portal_session(self, *, customer_id: str, return_url: str) -> str:
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
        )
        url = stripe_obj_get(session, "url")
        if not url:
            raise StripeServiceError("Billing portal session has no url")
        return str(url)

    def create_subscription_update_portal_session(
        self,
        *,
        customer_id: str,
        return_url: str,
        subscription_id: str,
        subscription_item_id: str,
        price_id: str,
    ) -> str:
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
            flow_data={
                "type": "subscription_update_confirm",
                "subscription_update_confirm": {
                    "subscription": subscription_id,
                    "items": [
                        {
                            "id": subscription_item_id,
                            "price": price_id,
                            "quantity": 1,
                        }
                    ],
                },
                "after_completion": {
                    "type": "redirect",
                    "redirect": {"return_url": return_url},
                },
            },
        )
        url = stripe_obj_get(session, "url")
        if not url:
            raise StripeServiceError("Billing portal session has no url")
        return str(url)

    def retrieve_subscription(self, subscription_id: str) -> Any:
        return stripe.Subscription.retrieve(subscription_id)

    def update_subscription(
        self,
        *,
        subscription_id: str,
        company_id: str,
        plan: str,
        interval: str,
        price_id: str,
    ) -> Any:
        subscription = stripe.Subscription.retrieve(subscription_id)
        item_id = subscription_item_id(subscription)
        if not item_id:
            raise StripeServiceError("Subscription has no items")
        return stripe.Subscription.modify(
            subscription_id,
            items=[{"id": item_id, "price": price_id, "quantity": 1}],
            proration_behavior="create_prorations",
            metadata={"company_id": company_id, "plan_type": plan, "interval": interval},
        )

    def verify_webhook(self, payload: bytes, signature: str) -> Any:
        secret = settings.STRIPE_WEBHOOK_SECRET
        if not secret:
            raise StripeServiceError("STRIPE_WEBHOOK_SECRET is not set")
        try:
            return stripe.Webhook.construct_event(payload, signature, secret)
        except Exception as exc:
            raise StripeServiceError(f"Invalid webhook signature: {exc}") from exc
