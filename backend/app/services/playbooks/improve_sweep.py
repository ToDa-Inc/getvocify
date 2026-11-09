"""The playbook's improvement step, run by itself: every hour, for each company that has it on, judge the cards of
finished calls and queue the answers that keep failing, exactly what the Playbook screen's refresh does by hand.

The work is bounded (a batch per company per sweep) and never touches a call in progress: `refresh_outcomes` only takes
cards whose call is closed and already read (see review_queue). Judging a card twice or queuing a case twice is not
possible, so a second server running the same sweep only repeats a read.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from app.services.feature_flags import global_value, is_enabled
from app.services.playbooks.assistant_store import AssistantUnavailable, get_assistant_store
from app.services.playbooks.review_queue import failing_by_answer, recent_outcomes, refresh_moments, refresh_outcomes

logger = logging.getLogger(__name__)

SWEEP_INTERVAL_SECONDS = 60 * 60
ASSISTANT_FLAG = "PLAYBOOK_ASSISTANT_ENABLED"
SUCCESS_FLAG = "PLAYBOOK_SUCCESS_RATE_ENABLED"
# A company with no live-help card in this long has nothing new to judge.
ACTIVE_DAYS = 2


def _candidates(supabase: Any) -> set[str]:
    """Companies that may have the step on: those with a row for either flag, and, when the flags are on for everyone,
    those that had live-help cards lately. Blocking."""
    ids: set[str] = set()
    rows = (
        supabase.table("company_feature_flags").select("company_id").in_("flag", [ASSISTANT_FLAG, SUCCESS_FLAG])
        .eq("enabled", True).execute()
    )
    ids.update(str(r["company_id"]) for r in getattr(rows, "data", None) or [] if r.get("company_id"))
    if global_value(ASSISTANT_FLAG) and global_value(SUCCESS_FLAG):
        since = (datetime.now(timezone.utc) - timedelta(days=ACTIVE_DAYS)).isoformat()
        recent = (
            supabase.table("live_assist_events").select("company_id").eq("is_objection", True).gte("created_at", since)
            .limit(2000).execute()
        )
        ids.update(str(r["company_id"]) for r in getattr(recent, "data", None) or [] if r.get("company_id"))
    return ids


async def sweep(supabase: Any) -> dict[str, dict]:
    """One pass -> {company_id: {judged, queued}} for the companies that have both flags on."""
    companies = await asyncio.to_thread(_candidates, supabase)
    store = get_assistant_store(supabase)
    done: dict[str, dict] = {}
    for company_id in sorted(companies):
        on = await asyncio.to_thread(
            lambda: is_enabled(supabase, company_id, ASSISTANT_FLAG) and is_enabled(supabase, company_id, SUCCESS_FLAG)
        )
        if not on:
            continue
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
