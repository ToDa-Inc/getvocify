"""The playbook's improvement step, run by itself: every hour, for every company that had live-help cards lately, judge
the cards of finished calls and queue the answers that keep failing, exactly what the Playbook screen's refresh does by
hand. Nobody has to switch it on (Dani, 2026-11-09); the screens that show the result keep their own flags.

The work is bounded (a batch per company per sweep) and never touches a call in progress: `refresh_outcomes` only takes
cards whose call is closed and already read (see review_queue). Judging a card twice or queuing a case twice is not
possible, so a second server running the same sweep only repeats a read.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from app.services.playbooks.assistant_store import AssistantUnavailable, get_assistant_store
from app.services.playbooks.review_queue import failing_by_answer, recent_outcomes, refresh_moments, refresh_outcomes

logger = logging.getLogger(__name__)

SWEEP_INTERVAL_SECONDS = 60 * 60
# A company with no live-help card in this long has nothing new to judge.
ACTIVE_DAYS = 2
SCAN = 5000


def _active_companies(supabase: Any) -> set[str]:
    """Companies with a live-help card about an objection or a question in the last ACTIVE_DAYS. Blocking."""
    since = (datetime.now(timezone.utc) - timedelta(days=ACTIVE_DAYS)).isoformat()
    rows = (
        supabase.table("live_assist_events").select("company_id").eq("is_objection", True).gte("created_at", since)
        .limit(SCAN).execute()
    )
    return {str(r["company_id"]) for r in getattr(rows, "data", None) or [] if r.get("company_id")}


async def sweep(supabase: Any) -> dict[str, dict]:
    """One pass -> {company_id: {judged, queued}}."""
    companies = await asyncio.to_thread(_active_companies, supabase)
    store = get_assistant_store(supabase)
    done: dict[str, dict] = {}
    for company_id in sorted(companies):
        try:
            judged = await refresh_outcomes(store, supabase, company_id)
            queued = await asyncio.to_thread(
                lambda: refresh_moments(store, company_id, failing_by_answer(recent_outcomes(store, company_id, after_fixes=True)))
            )
        except AssistantUnavailable:
            logger.warning("playbook improvement sweep: assistant store unavailable")
            return done
        except Exception:
            logger.exception("playbook improvement sweep failed for a company", extra={"domain": "playbooks", "company_id": company_id})
            continue
        done[company_id] = {"judged": judged, "queued": queued}
    return done
