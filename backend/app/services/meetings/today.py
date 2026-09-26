"""Hoy meeting_today signals from accepted F14 proposals. Read-only, no model call."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from app.services.feature_flags import is_enabled
from app.services.hoy.materialize import HOY_MEMO_LIMIT, as_dt
from app.services.hoy.reconcile import plan_reconcile
from app.services.hoy.signals import Signal

logger = logging.getLogger(__name__)

MEETINGS_FLAG = "HOY_MEETINGS_ENABLED"
MEETING_TYPE = "meeting_today"
DEFAULT_TZ = "Europe/Madrid"


def meeting_dedupe_key(proposal_id: str) -> str:
    return f"meeting_today:{proposal_id}"


def _local_date(value: datetime, tz_name: str):
    return value.astimezone(ZoneInfo(tz_name or DEFAULT_TZ)).date()


def _card_precision(precision: str | None, starts_at: datetime | None) -> str:
    raw = str(precision or "").lower()
    if raw in {"date_only", "date"}:
        return "date"
    if starts_at is None:
        return "date"
    return "time"


def _meeting_title(memo: dict) -> str:
    extraction = memo.get("extraction") if isinstance(memo.get("extraction"), dict) else {}
    intelligence = extraction.get("intelligence") if isinstance(extraction.get("intelligence"), dict) else {}
    meeting = intelligence.get("meeting") if isinstance(intelligence.get("meeting"), dict) else {}
    for key in ("title", "text", "label"):
        text = " ".join(str(meeting.get(key) or "").split())
        if text:
            return text
    summary = " ".join(str(extraction.get("summary") or "").split())
    return summary


def _accepted_at(memo: dict, proposal: dict) -> datetime | None:
    for key in ("approved_at", "updated_at", "created_at"):
        parsed = as_dt(memo.get(key))
        if parsed is not None:
            return parsed
    return as_dt(proposal.get("created_at"))


def _is_today(starts_at: datetime | None, *, now: datetime, tz_name: str) -> bool:
    if starts_at is None:
        return False
    return _local_date(starts_at, tz_name) == _local_date(now, tz_name)


def meeting_today_signal(
    proposal: dict,
    memo: dict,
    *,
    now: datetime,
    tz_name: str,
) -> Signal | None:
    """One accepted proposal becomes one card when its starts_at is today in the rep zone."""
    if proposal.get("decision") != "accepted" or proposal.get("agreement") != "agreed":
        return None
    starts_raw = proposal.get("starts_at")
    starts_at = as_dt(starts_raw)
    if not _is_today(starts_at, now=now, tz_name=tz_name):
        return None
    contact_id = memo.get("hubspot_contact_id") or memo.get("contact_id")
    if not contact_id:
        return None
    precision = _card_precision(proposal.get("precision"), starts_at)
    accepted = _accepted_at(memo, proposal)
    payload = {
        "starts_at": starts_raw,
        "precision": precision,
        "accepted_at": accepted.isoformat() if accepted else None,
        "title": _meeting_title(memo),
        "proposal_id": proposal.get("proposal_id"),
    }
    return Signal(
        MEETING_TYPE,
        contact_id=str(contact_id),
        deal_id=str(memo.get("hubspot_deal_id")) if memo.get("hubspot_deal_id") else None,
        source_memo_id=str(memo.get("id") or ""),
        due_at=starts_at,
        payload=payload,
        dedupe_key=meeting_dedupe_key(str(proposal.get("proposal_id") or "")),
        connection_id=str(memo.get("connection_id") or "") or None,
    )


def collect_meeting_today(
    proposals: list[dict],
    memos_by_id: dict[str, dict],
    *,
    now: datetime,
    tz_name: str,
) -> list[Signal]:
    fresh: list[Signal] = []
    seen: set[str] = set()
    for proposal in proposals:
        memo = memos_by_id.get(str(proposal.get("memo_id") or ""))
        if memo is None:
            continue
        signal = meeting_today_signal(proposal, memo, now=now, tz_name=tz_name)
        if signal is None or signal.dedupe_key in seen:
            continue
        seen.add(signal.dedupe_key)
        fresh.append(signal)
    fresh.sort(key=lambda item: (item.due_at or now).timestamp())
    return fresh


def _read_memos(supabase, *, company_id: str, user_id: str) -> list[dict]:
    try:
        stored = (
            supabase.table("memos")
            .select(
                "id,hubspot_contact_id,hubspot_deal_id,connection_id,extraction,"
                "capture_started_at,created_at,updated_at,approved_at"
            )
            .eq("user_id", user_id)
            .or_(f"company_id.eq.{company_id},company_id.is.null")
            .order("created_at", desc=True)
            .limit(HOY_MEMO_LIMIT)
            .execute()
        )
    except Exception:
        logger.warning("meeting_today memo read failed", exc_info=True)
        return []
    return list(stored.data or [])


def _load_proposals(supabase, memo_ids: list[str]) -> list[dict]:
    if not memo_ids:
        return []
    try:
        stored = (
            supabase.table("meeting_proposals")
            .select("*")
            .in_("memo_id", memo_ids)
            .eq("decision", "accepted")
            .execute()
        )
    except Exception:
        logger.warning("meeting_today proposal read failed", exc_info=True)
        return []
    return list(stored.data or [])


def refresh_meeting_today(
    supabase,
    *,
    company_id: str,
    user_id: str,
    now: datetime,
    tz_name: str,
) -> int:
    """Materialize meeting_today signals for accepted proposals. Idempotent upsert."""
    if not is_enabled(supabase, company_id, MEETINGS_FLAG):
        return 0
    try:
        memos = _read_memos(supabase, company_id=company_id, user_id=user_id)
        memo_ids = [str(memo.get("id") or "") for memo in memos if memo.get("id")]
        memos_by_id = {str(memo.get("id") or ""): memo for memo in memos}
        proposals = _load_proposals(supabase, memo_ids)
        stored = (
            supabase.table("action_signals")
            .select("*")
            .eq("company_id", company_id)
            .eq("user_id", user_id)
            .eq("type", MEETING_TYPE)
            .execute()
        ).data or []
    except Exception:
        logger.warning("meeting_today refresh failed", exc_info=True)
        return 0

    fresh = collect_meeting_today(proposals, memos_by_id, now=now, tz_name=tz_name)
    plan = plan_reconcile(stored=stored, fresh=fresh, now=now, source_available=True)
    inserted = 0
    by_key = {row.get("dedupe_key"): row for row in stored}
    for signal in plan["insert"]:
        supabase.table("action_signals").upsert(
            {
                "company_id": company_id,
                "user_id": user_id,
                "connection_id": signal.connection_id or "",
                "contact_id": signal.contact_id,
                "deal_id": signal.deal_id,
                "memo_id": signal.source_memo_id,
                "type": signal.type,
                "dedupe_key": signal.dedupe_key,
                "payload": {
                    **signal.payload,
                    **({"due_at": signal.due_at.isoformat()} if signal.due_at else {}),
                },
                "status": "pending",
                "coverage": "complete",
            },
            on_conflict="company_id,user_id,connection_id,dedupe_key",
            ignore_duplicates=True,
        ).execute()
        inserted += 1
    if not fresh:
        return inserted
    for key in plan["resolve"]:
        row = by_key.get(key)
        if not row:
            continue
        version = int(row.get("version") or 1)
        (
            supabase.table("action_signals")
            .update({
                "status": "resolved",
                "previous_status": row.get("status"),
                "version": version + 1,
            })
            .eq("id", row["id"])
            .eq("version", version)
            .execute()
        )
    return inserted
