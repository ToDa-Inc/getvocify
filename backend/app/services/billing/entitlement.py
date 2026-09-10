"""Workspace billing entitlement. Company policy vs Stripe snapshot."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.services.billing.catalog import plan_from_product_id

ACCESS_OPEN = "open"
PLAN_TYPES = frozenset({"starter", "pro"})
ACCESS_PAYWALLED = "paywalled"
ACCESS_UNLOCKED = "unlocked"
ACCESS_MODES = frozenset({ACCESS_OPEN, ACCESS_PAYWALLED, ACCESS_UNLOCKED})

PAID_STATUSES = frozenset({"active", "trialing"})
PAST_DUE_GRACE = timedelta(days=3)
KNOWN_BILLING_STATUSES = frozenset(
    {"none", "active", "trialing", "past_due", "canceled", "unpaid", "incomplete"}
)
STRIPE_STATUS_MAP = {
    "active": "active",
    "trialing": "trialing",
    "past_due": "past_due",
    "canceled": "canceled",
    "unpaid": "unpaid",
    "incomplete": "incomplete",
    "incomplete_expired": "canceled",
    "paused": "unpaid",
}


def access_mode_of(company: Optional[dict]) -> str:
    mode = (company or {}).get("access_mode") or ACCESS_OPEN
    return mode if mode in ACCESS_MODES else ACCESS_OPEN


def billing_status_of(billing: Optional[dict]) -> str:
    status = (billing or {}).get("billing_status") or "none"
    return status if status in KNOWN_BILLING_STATUSES else "none"


def plan_type_of(billing: Optional[dict]) -> Optional[str]:
    raw = (billing or {}).get("plan_type")
    return raw if raw in PLAN_TYPES else None


def is_paid_or_grace(billing: Optional[dict], *, now: Optional[datetime] = None) -> bool:
    if billing_status_of(billing) in PAID_STATUSES:
        return True
    return in_past_due_grace(billing, now=now)


def can_use_dialer(
    company: Optional[dict],
    billing: Optional[dict] = None,
    *,
    now: Optional[datetime] = None,
) -> bool:
    """Pro on a live sub, unlocked workspaces, or open workspaces that have not subscribed."""
    if access_mode_of(company) == ACCESS_UNLOCKED:
        return True
    if is_paid_or_grace(billing, now=now):
        return plan_type_of(billing) == "pro"
    return access_mode_of(company) == ACCESS_OPEN


def workspace_entitlements(
    company: Optional[dict],
    billing: Optional[dict] = None,
    *,
    now: Optional[datetime] = None,
) -> dict:
    return {
        "access_mode": access_mode_of(company),
        "billing_status": billing_status_of(billing),
        "plan_type": plan_type_of(billing),
        "paywalled": is_paywalled(company, billing, now=now),
        "can_use_dialer": can_use_dialer(company, billing, now=now),
    }


def _parse_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def in_past_due_grace(billing: Optional[dict], *, now: Optional[datetime] = None) -> bool:
    if billing_status_of(billing) != "past_due":
        return False
    since = _parse_dt((billing or {}).get("past_due_since"))
    if since is None:
        return False
    current = now or datetime.now(timezone.utc)
    return current <= since + PAST_DUE_GRACE


def is_paywalled(
    company: Optional[dict],
    billing: Optional[dict] = None,
    *,
    now: Optional[datetime] = None,
) -> bool:
    if not company:
        return False
    if access_mode_of(company) != ACCESS_PAYWALLED:
        return False
    status = billing_status_of(billing)
    if status in PAID_STATUSES:
        return False
    if in_past_due_grace(billing, now=now):
        return False
    return True


def normalize_billing_status(stripe_status: Optional[str]) -> str:
    if not stripe_status:
        return "none"
    return STRIPE_STATUS_MAP.get(str(stripe_status).lower(), "none")


def stripe_obj_get(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _first_subscription_item(subscription: Any) -> Any:
    items = stripe_obj_get(subscription, "items")
    if items is None:
        return None
    data = stripe_obj_get(items, "data") if not isinstance(items, list) else items
    if not data:
        return None
    return data[0]


def subscription_quantity(subscription: Any) -> int:
    item = _first_subscription_item(subscription)
    raw = stripe_obj_get(item, "quantity", 1) if item is not None else 1
    try:
        qty = int(raw or 1)
    except (TypeError, ValueError):
        qty = 1
    return max(1, qty)


def subscription_item_id(subscription: Any) -> Optional[str]:
    item = _first_subscription_item(subscription)
    if item is None:
        return None
    value = stripe_obj_get(item, "id")
    return str(value) if value else None


def subscription_interval(subscription: Any) -> Optional[str]:
    item = _first_subscription_item(subscription)
    price = stripe_obj_get(item, "price") if item is not None else None
    recurring = stripe_obj_get(price, "recurring") if price is not None else None
    raw = stripe_obj_get(recurring, "interval") if recurring is not None else None
    if raw == "year":
        return "yearly"
    if raw == "month":
        return "monthly"
    return None


def subscription_product_id(subscription: Any) -> Optional[str]:
    item = _first_subscription_item(subscription)
    price = stripe_obj_get(item, "price") if item is not None else None
    product = stripe_obj_get(price, "product") if price is not None else None
    if product is None:
        return None
    if isinstance(product, str):
        return product
    value = stripe_obj_get(product, "id")
    return str(value) if value else None


def subscription_plan_type(subscription: Any) -> Optional[str]:
    meta = stripe_obj_get(subscription, "metadata") or {}
    if isinstance(meta, dict):
        raw = meta.get("plan_type")
        if raw in PLAN_TYPES:
            return str(raw)
    return plan_from_product_id(subscription_product_id(subscription))


def subscription_period_end(subscription: Any) -> Optional[datetime]:
    raw = stripe_obj_get(subscription, "current_period_end")
    parsed = _parse_dt(raw)
    if parsed:
        return parsed
    item = _first_subscription_item(subscription)
    return _parse_dt(stripe_obj_get(item, "current_period_end")) if item is not None else None


def company_id_from_stripe_object(obj: Any) -> Optional[str]:
    if obj is None:
        return None
    meta = stripe_obj_get(obj, "metadata") or {}
    if isinstance(meta, dict):
        cid = meta.get("company_id")
        if cid:
            return str(cid)
    ref = stripe_obj_get(obj, "client_reference_id")
    return str(ref) if ref else None


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def billing_row_from_subscription(
    subscription: Any,
    *,
    deleted: bool = False,
    existing: Optional[dict] = None,
    now: Optional[datetime] = None,
) -> dict:
    """Local company_billing snapshot. Does not touch companies.seat_limit."""
    status = "canceled" if deleted else normalize_billing_status(
        stripe_obj_get(subscription, "status")
    )
    current = now or datetime.now(timezone.utc)
    existing_status = billing_status_of(existing)
    past_due_since = None
    if status == "past_due":
        if existing_status == "past_due":
            past_due_since = (existing or {}).get("past_due_since") or _iso(current)
        else:
            past_due_since = _iso(current)

    customer = stripe_obj_get(subscription, "customer")
    customer_id = customer if isinstance(customer, str) else stripe_obj_get(customer, "id")
    cancel_flag = stripe_obj_get(subscription, "cancel_at_period_end")
    plan_type = subscription_plan_type(subscription) or (existing or {}).get("plan_type")
    if plan_type not in PLAN_TYPES:
        plan_type = None
    row = {
        "stripe_subscription_id": stripe_obj_get(subscription, "id"),
        "billing_status": status,
        "billing_interval": subscription_interval(subscription),
        "plan_type": plan_type,
        "quantity": subscription_quantity(subscription) if not deleted else (existing or {}).get("quantity"),
        "current_period_end": _iso(subscription_period_end(subscription)),
        "cancel_at_period_end": bool(cancel_flag),
        "past_due_since": past_due_since,
    }
    if customer_id:
        row["stripe_customer_id"] = str(customer_id)
    return row


def should_sync_seat_limit(company: dict, billing_row: dict, *, deleted: bool = False) -> bool:
    """Flat workspace plans. Seat cap stays on companies.seat_limit (admin)."""
    return False
