"""Hoy meeting_today signals from accepted F14 proposals. Read-only, no model call."""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.feature_flags import is_enabled
from app.services.hoy.materialize import HOY_MEMO_LIMIT, as_dt
from app.services.hoy.reconcile import plan_reconcile
from app.services.hoy.signals import Signal

logger = logging.getLogger(__name__)

MEETINGS_FLAG = "HOY_MEETINGS_ENABLED"
MEETING_TYPE = "meeting_today"
DEFAULT_TZ = "Europe/Madrid"
# F14 stores the rep-corrected time on the row and keeps its original precision.
_ACCEPTED = frozenset({"accepted", "corrected"})


def meeting_dedupe_key(proposal_id: str) -> str:
    return f"meeting_today:{proposal_id}"


def _local_date(value: datetime, tz_name: str):
    return value.astimezone(ZoneInfo(tz_name or DEFAULT_TZ)).date()


def _accepted_at(memo: dict, proposal: dict) -> datetime | None:
    """No column stores the acceptance: the approval of the review that accepted it, else the proposal."""
    return as_dt(memo.get("approved_at")) or as_dt(proposal.get("created_at"))


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
    decision = proposal.get("decision")
    if decision not in _ACCEPTED:
        return None
    if decision == "accepted" and proposal.get("agreement") != "agreed":
        return None
    starts_raw = proposal.get("starts_at")
    starts_at = as_dt(starts_raw)
    if not _is_today(starts_at, now=now, tz_name=tz_name):
        return None
    contact_id = memo.get("hubspot_contact_id") or memo.get("contact_id")
    if not contact_id:
        return None
    accepted = _accepted_at(memo, proposal)
    payload = {
        "starts_at": starts_raw,
        "precision": "time",
        "accepted_at": accepted.isoformat() if accepted else None,
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


def latest_revisions(proposals: list[dict]) -> list[dict]:
    """The newest revision of each proposal, ordered as `latest_proposal` orders them."""
    newest: dict[tuple[str, str], dict] = {}
    for row in proposals:
        key = (str(row.get("memo_id") or ""), str(row.get("proposal_id") or ""))
        rank = str(row.get("created_at") or row.get("input_revision") or "")
        current = newest.get(key)
        if current is None or rank > str(current.get("created_at") or current.get("input_revision") or ""):
            newest[key] = row
    return list(newest.values())


def collect_meeting_today(
    proposals: list[dict],
    memos_by_id: dict[str, dict],
    *,
    now: datetime,
    tz_name: str,
) -> list[Signal]:
    fresh: list[Signal] = []
    seen: set[str] = set()
    for proposal in latest_revisions(proposals):
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
    stored = (
        supabase.table("memos")
        .select("id,hubspot_contact_id,hubspot_deal_id,created_at,approved_at")
        .eq("user_id", user_id)
        .or_(f"company_id.eq.{company_id},company_id.is.null")
        .order("created_at", desc=True)
        .limit(HOY_MEMO_LIMIT)
        .execute()
    )
    return list(stored.data or [])


def _load_proposals(supabase, memo_ids: list[str]) -> list[dict]:
    """Every revision: a newer pending revision hides an older accepted one."""
    if not memo_ids:
        return []
    stored = (
        supabase.table("meeting_proposals")
        .select("*")
        .in_("memo_id", memo_ids)
        .execute()
    )
    return list(stored.data or [])


def refresh_meeting_today(
    supabase,
    *,
    company_id: str,
    user_id: str,
    now: datetime,
    tz_name: str,
) -> int:
    """Materialize today's meetings and resolve the ones that are no longer today. A failed read resolves nothing."""
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
