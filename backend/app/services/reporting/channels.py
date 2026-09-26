"""Conversations held per channel. Voicemail and no-answer were never a conversation."""

from __future__ import annotations

import logging
from datetime import datetime

from app.services.captures import interaction_kind_of

logger = logging.getLogger(__name__)

CHANNELS = ("call", "meeting", "visit")
CHANNEL_MEMO_COLUMNS = "id,user_id,company_id,source,source_type,interaction_kind,screening_outcome,capture_started_at,created_at"
_NOT_REACHED = frozenset({"voicemail", "no_response"})


def _captured_at(memo: dict) -> str | None:
    value = memo.get("capture_started_at") or memo.get("created_at")
    if value is None:
        return None
    text = value.isoformat() if hasattr(value, "isoformat") else str(value).strip()
    return text or None


def interaction_channels(memos: list[dict], *, start: datetime, end: datetime) -> dict[str, int]:
    """Only dialer calls carry screening; other calls are recordings of a conversation that happened."""
    start_s, end_s = start.isoformat(), end.isoformat()
    counts = {channel: 0 for channel in CHANNELS}
    for memo in memos:
        captured = _captured_at(memo)
        if captured is None or captured < start_s or captured >= end_s:
            continue
        if memo.get("screening_outcome") in _NOT_REACHED:
            continue
        kind = interaction_kind_of(memo)
        if kind in counts:
            counts[kind] += 1
    return counts


def load_team_channel_memos(supabase, company_id: str, member_ids: list[str]) -> list[dict] | None:
    """Same scope as the team panel: members' memos, including older ones without company_id. None on failure."""
    try:
        query = supabase.table("memos").select(CHANNEL_MEMO_COLUMNS)
        if member_ids:
            query = query.in_("user_id", member_ids).or_(f"company_id.eq.{company_id},company_id.is.null")
        else:
            query = query.eq("company_id", company_id)
        return list(query.execute().data or [])
    except Exception:
        logger.exception("team report: load channel memos failed")
        return None
