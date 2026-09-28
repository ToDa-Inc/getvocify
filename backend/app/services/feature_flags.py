"""Per-company overrides of the global switches in config.py (table company_feature_flags)."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Optional

from app.config import settings

logger = logging.getLogger(__name__)

TTL_SECONDS = 60.0
_now = time.monotonic
_cache: dict[str, tuple[float, dict[str, bool]]] = {}
_lock = threading.Lock()


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def global_value(flag: str) -> bool:
    return bool(getattr(settings, flag, False))


def _overrides(supabase: Any, company_id: str) -> dict[str, bool]:
    now = _now()
    with _lock:
        hit = _cache.get(company_id)
    if hit and now - hit[0] < TTL_SECONDS:
        return hit[1]
    result = (
        supabase.table("company_feature_flags")
        .select("flag,enabled")
        .eq("company_id", company_id)
        .execute()
    )
    flags = {
        str(row["flag"]): bool(row["enabled"])
        for row in (getattr(result, "data", None) or [])
        if row.get("flag") and row.get("enabled") is not None
    }
    with _lock:
        _cache[company_id] = (now, flags)
    return flags


# Lista 3 flags exposed to the frontend as company.features (GET /auth/me). Kept in one
# place so T1's helper and each later task's flag stay in sync without hunting config.py.
LISTA_3_FLAGS: tuple[str, ...] = (
    "SALES_ROLES_ENABLED",
    "HANDOFF_ENABLED",
    "HANDOFF_CRM_OWNER_ENABLED",
    "HOY_LEAD_TIERS_ENABLED",
    "HOY_AE_DEALS_ENABLED",
    "FOLLOWUP_SEND_ENABLED",
    "FOLLOWUP_BY_FLOW_ENABLED",
    "ONBOARDING_WIZARD_ENABLED",
    "SCORING_OBJECTION_CREDIT_ENABLED",
    "DEBRIEF_V2_ENABLED",
    "PLAYBOOK_TAB_ENABLED",
    "REPORTING_BY_FLOW_ENABLED",
    "BELL_TASKS_ENABLED",
    "MANAGER_HOME_ENABLED",
    "RECALL_BOT_ENABLED",
)
# Lista 4 flags, exposed the same way.
LISTA_4_FLAGS: tuple[str, ...] = (
    "HOY_SDR_SECTIONS_ENABLED",
    "BRIEF_COMPANY_HOOK_ENABLED",
    "AFTER_CALL_FLOW_ENABLED",
    "COACHING_MESSAGES_ENABLED",
)
CLIENT_FLAGS: tuple[str, ...] = LISTA_3_FLAGS + LISTA_4_FLAGS


def enabled_features(supabase: Any, company_id: Optional[str], names: "list[str] | tuple[str, ...]") -> list[str]:
    """Names from `names` that are enabled for this company. Order preserved."""
    return [name for name in names if is_enabled(supabase, company_id, name)]


def is_enabled(supabase: Any, company_id: Optional[str], flag: str) -> bool:
    """The company override if set, else the global value. A failed lookup is the global value."""
    default = global_value(flag)
    if not company_id:
        return default
    try:
        return _overrides(supabase, str(company_id)).get(flag, default)
    except Exception:
        logger.warning(
            "feature flag lookup failed flag=%s", flag,
            extra={"flag": flag, "company_id": str(company_id)},
            exc_info=True,
        )
        return default
