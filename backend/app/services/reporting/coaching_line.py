"""Coaching line of a rep's own report (COACHING_MESSAGES_ENABLED). Reads through the rep
coaching engine; any failure means no line, never a broken report."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from app.services.coaching import rep_coaching as engine
from app.services.coaching import rep_coaching_reads as reads
from app.services.coaching.rep_focus import flow_window_start, in_window, previous_week_start, rep_focus, rows_of
from app.services.coaching.rep_messages import daily_coaching_line, weekly_coaching_line
from app.services.company import sales_role_for_user
from app.services.feature_flags import is_enabled
from app.services.team_insights.aggregate import madrid_week_bounds

logger = logging.getLogger(__name__)

FLAG = "COACHING_MESSAGES_ENABLED"


def _context(supabase, company_id: str, user_id: str, *, reference: datetime, since: datetime):
    week_start, week_end = madrid_week_bounds(now=reference)
    prev_start = previous_week_start(week_start)
    # The same FLOW_WEEKS window as the coaching tab, so a general rep gets the same flow.
    rows = rows_of(reads.load_memos(supabase, company_id, [user_id], start=min(since, flow_window_start(week_start))))
    playbooks: dict[str, dict] = {}

    def playbook_for(motion: str) -> dict:
        if motion not in playbooks:
            playbooks[motion] = reads.load_published_playbook(supabase, company_id, motion)
        return playbooks[motion]

    role = sales_role_for_user(supabase, user_id, company_id=company_id)
    return rows, role, playbook_for, prev_start, week_start


def self_daily_coaching(
    supabase, *, company_id: str, user_id: str, period_start: datetime, period_end: datetime
) -> str | None:
    if not is_enabled(supabase, company_id, FLAG):
        return None
    try:
        rows, role, playbook_for, prev_start, week_start = _context(
            supabase, company_id, user_id, reference=period_start, since=period_start
        )
        found = rep_focus(rows, role, playbook_for, prev_start=prev_start, week_start=week_start)
        if found is None:
            return None
        day = [r for r in in_window(rows, period_start, period_end) if r["motion"] == found["motion"]]
        return daily_coaching_line(day, found["steps"], found["focus"])
    except Exception:
        logger.exception("daily report: coaching line failed")
        return None


def self_weekly_coaching(
    supabase, *, company_id: str, user_id: str, period_start: datetime, period_end: datetime
) -> str | None:
    if not is_enabled(supabase, company_id, FLAG):
        return None
    try:
        rows, role, playbook_for, _, _ = _context(
            supabase, company_id, user_id, reference=period_start, since=period_start - timedelta(days=8)
        )
        # The focus in force during the reported week came from the week before it; the
        # new one is chosen over the reported week itself.
        found = rep_focus(
            rows, role, playbook_for, prev_start=previous_week_start(period_start), week_start=period_start
        )
        if found is None:
            return None
        week = [r for r in in_window(rows, period_start, period_end) if r["motion"] == found["motion"]]
        new_focus = engine.choose_focus(week, found["steps"])
        return weekly_coaching_line(found["focus"], week, found["steps"], new_focus)
    except Exception:
        logger.exception("weekly report: coaching line failed")
        return None
