"""Conversations held per channel. Voicemail and no-answer were never a conversation."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from app.services.captures import interaction_kind_of

logger = logging.getLogger(__name__)

CHANNELS = ("call", "meeting", "visit")
CHANNEL_MEMO_COLUMNS = "id,user_id,company_id,source,source_type,interaction_kind,screening_outcome,capture_started_at,created_at"
_NOT_REACHED = frozenset({"voicemail", "no_response"})
_CREATED_AFTER_CAPTURE_SLACK = timedelta(days=1)


def _is_conversation(memo: dict) -> bool:
    """A dialer call is a conversation only once screening says connected; other calls are recordings of one."""
    screening = memo.get("screening_outcome")
    if memo.get("source") == "vocify_call":
        return screening == "connected"
    return screening not in _NOT_REACHED


def interaction_channels(memos: list[dict], *, start: datetime, end: datetime) -> dict[str, int]:
    from app.services.reporting.daily_snapshot import _memos_in_period

    counts = {channel: 0 for channel in CHANNELS}
    for memo in _memos_in_period(memos, start, end):
        if not _is_conversation(memo):
            continue
        kind = interaction_kind_of(memo)
        if kind in counts:
            counts[kind] += 1
    return counts


def load_team_channel_memos(
    supabase, company_id: str, member_ids: list[str], *, start: datetime, end: datetime
) -> list[dict] | None:
    """Same scope as the team panel. None on failure.

    The period is capture_started_at or created_at, and capture_started_at <= created_at: created_at >= start
    loses nothing, and the upper bound leaves slack for captures that end up stored after the period closes.
    """
    try:
        query = (
            supabase.table("memos")
            .select(CHANNEL_MEMO_COLUMNS)
            .gte("created_at", start.isoformat())
            .lt("created_at", (end + _CREATED_AFTER_CAPTURE_SLACK).isoformat())
        )
        if member_ids:
            query = query.in_("user_id", member_ids).or_(f"company_id.eq.{company_id},company_id.is.null")
        else:
            query = query.eq("company_id", company_id)
        return list(query.execute().data or [])
    except Exception:
        logger.exception("team report: load channel memos failed")
        return None
