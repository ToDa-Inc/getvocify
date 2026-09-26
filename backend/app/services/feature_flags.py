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
