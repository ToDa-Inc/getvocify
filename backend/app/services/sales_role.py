"""Normalize sales_role values for company members and invites."""
from __future__ import annotations

from typing import Optional

SALES_ROLE_VALUES = frozenset({"sdr", "ae", "general"})


def normalize_sales_role(value: Optional[str]) -> str:
    """Return sdr, ae, or general; anything else (None, empty, unknown) → general."""
    if value in SALES_ROLE_VALUES:
        return value  # type: ignore[return-value]
    return "general"
