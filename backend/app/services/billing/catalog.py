"""Workspace plans. Product ids are the Stripe source; prices resolve at checkout."""

from __future__ import annotations

from typing import Literal, Optional

PlanId = Literal["starter", "pro"]
Interval = Literal["monthly", "yearly"]

PLANS: tuple[PlanId, ...] = ("starter", "pro")
INTERVALS: tuple[Interval, ...] = ("monthly", "yearly")

PRODUCTS: dict[tuple[PlanId, Interval], str] = {
    ("starter", "monthly"): "prod_VENfYYKhSV2KAB",
    ("pro", "monthly"): "prod_VENfWDk6BSnMIy",
    ("starter", "yearly"): "prod_VENgF43xTwG3OT",
    ("pro", "yearly"): "prod_VENgP2K1H6YO7c",
}

AMOUNT_CENTS: dict[tuple[PlanId, Interval], int] = {
    ("starter", "monthly"): 3900,
    ("pro", "monthly"): 5900,
    ("starter", "yearly"): 39000,
    ("pro", "yearly"): 59000,
}

PRODUCT_TO_PLAN: dict[str, PlanId] = {
    product_id: plan for (plan, _interval), product_id in PRODUCTS.items()
}

SHARED_FEATURES = (
    "Transcriptions, word-perfect",
    "Summaries that land",
    "CRM that writes itself",
    "Tasks, already queued",
    "Follow-ups, ready to send",
    "Scoring you can stand on",
    "Coaching as it happens",
)

PRO_DIALER_FEATURE = "Dialer included — 1,000 minutes"

PLAN_COPY = {
    "starter": {
        "name": "Starter",
        "tagline": "Every conversation, captured and closed.",
    },
    "pro": {
        "name": "Pro",
        "tagline": "The same craft, plus a dialer that goes the distance.",
    },
}


def is_plan(value: str) -> bool:
    return value in PLANS


def is_interval(value: str) -> bool:
    return value in INTERVALS


def product_id_for(plan: str, interval: str) -> str:
    if not is_plan(plan) or not is_interval(interval):
        raise ValueError("Unknown plan or interval")
    return PRODUCTS[(plan, interval)]  # type: ignore[index]


def plan_from_product_id(product_id: Optional[str]) -> Optional[PlanId]:
    if not product_id:
        return None
    return PRODUCT_TO_PLAN.get(str(product_id))


def amount_euros(plan: str, interval: str) -> int:
    cents = AMOUNT_CENTS[(plan, interval)]  # type: ignore[index]
    return cents // 100


def yearly_monthly_amount(monthly: int, yearly: int) -> int:
    return (yearly + 6) // 12


def yearly_discount_percent(monthly: int, yearly: int) -> int:
    full = monthly * 12
    if full <= 0:
        return 0
    return max(0, round((full - yearly) / full * 100))


def _plan_amounts(plan: str) -> dict:
    monthly = amount_euros(plan, "monthly")
    yearly = amount_euros(plan, "yearly")
    return {
        "monthly_amount": monthly,
        "yearly_amount": yearly,
        "yearly_monthly_amount": yearly_monthly_amount(monthly, yearly),
        "yearly_discount_percent": yearly_discount_percent(monthly, yearly),
    }


def catalog_payload() -> dict:
    starter = _plan_amounts("starter")
    pro = _plan_amounts("pro")
    return {
        "currency": "eur",
        "yearly_discount_percent": max(starter["yearly_discount_percent"], pro["yearly_discount_percent"]),
        "plans": [
            {
                "id": "starter",
                "name": PLAN_COPY["starter"]["name"],
                "tagline": PLAN_COPY["starter"]["tagline"],
                **starter,
                "features": list(SHARED_FEATURES),
                "includes_dialer": False,
            },
            {
                "id": "pro",
                "name": PLAN_COPY["pro"]["name"],
                "tagline": PLAN_COPY["pro"]["tagline"],
                **pro,
                "features": [*SHARED_FEATURES, PRO_DIALER_FEATURE],
                "includes_dialer": True,
                "dialer_minutes": 1000,
            },
        ],
    }
