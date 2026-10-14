"""The team's own objections (custom playbook entries), for the turn check.

The turn check knows a fixed list of objection kinds. A playbook can add its own («Nuestra venta es
muy diferente», «Mándame un email»): without them the classifier calls those turns "none" and no card
shows, however good the approved answer is. They come from the rep's published playbook for the
call's type, never from a list in code.

The check runs on every pause, so the lookup is cached for a short time per rep and type.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

CACHE_SECONDS = 60.0
_MAX_CACHED = 500
_cache: dict[tuple[str, str], tuple[float, dict[str, dict[str, str]]]] = {}
# The company each rep was last seen in, so the event log knows it without a lookup of its own.
_company: dict[str, str] = {}


def company_of(user_id: str) -> Optional[str]:
    return _company.get(user_id)


def custom_entries(snapshot: Optional[dict]) -> dict[str, dict[str, str]]:
    """{entry_id: {label, trigger}} of the snapshot's custom entries that have an answer to give."""
    found: dict[str, dict[str, str]] = {}
    for entry in (snapshot or {}).get("entries") or []:
        if not isinstance(entry, dict) or str(entry.get("category") or "") != "custom":
            continue
        entry_id = str(entry.get("entry_id") or "").strip()
        label = " ".join(str(entry.get("label") or "").split())
        trigger = " ".join(str(entry.get("trigger") or "").split())
        if entry_id and label and str(entry.get("guidance") or "").strip():
            found[entry_id] = {"label": label, "trigger": trigger}
    return found


def custom_for(supabase: Any, user_id: str, sales_motion_key: str) -> dict[str, dict[str, str]]:
    """The custom objections of the playbook this rep's call of this type uses; {} when there are none
    or anything fails (a failed lookup must never get in the way of a call). Blocking: run it in a thread."""
    key = (user_id, sales_motion_key)
    cached = _cache.get(key)
    if cached and time.monotonic() - cached[0] < CACHE_SECONDS:
        return cached[1]
    found: dict[str, dict[str, str]] = {}
    try:
        from app.services.company import CompanyService
        from app.services.playbooks.live import live_snapshot

        membership = CompanyService(supabase).require_membership(user_id)
        _company[user_id] = membership.company_id
        found = custom_entries(live_snapshot(supabase, membership.company_id, sales_motion_key))
    except Exception:
        # Not kept: the next check tries again.
        logger.warning("turn check: custom objections lookup failed", exc_info=True)
        return found
    if len(_cache) >= _MAX_CACHED:
        _cache.clear()
    _cache[key] = (time.monotonic(), found)
    return found
