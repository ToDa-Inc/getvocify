"""Materialize self daily reports from memos before the email tick loads rows."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from app.services.company import sales_role_for_user
from app.services.feature_flags import is_enabled
from app.services.reporting.aggregate import build_snapshot
from app.services.reporting.channels import interaction_channels
from app.services.reporting.coaching_line import self_daily_coaching
from app.services.reporting.delivery import period_bounds
from app.services.reporting.due_sends import MADRID
from app.services.reporting.preferences import is_opted_in, load_preference_rows

logger = logging.getLogger(__name__)

_SCREENING = frozenset({"voicemail", "no_response", "connected"})
_MEETING_KINDS = frozenset({"meeting", "visit"})
FLOW_FLAG = "REPORTING_BY_FLOW_ENABLED"


def _parse_iso(value) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    text = str(value).strip()
    return text or None


def _interaction_from_memo(memo: dict) -> dict | None:
    screening = memo.get("screening_outcome")
    if screening not in _SCREENING:
        return None
    captured = _parse_iso(memo.get("capture_started_at") or memo.get("created_at"))
    if captured is None:
        return None
    memo_id = memo.get("id")
    if not memo_id:
        return None
    return {
        "memo_id": str(memo_id),
        "captured_at": captured,
        "screening": screening,
        # Connected and someone talked (not a voicemail or silence the call reading caught): coaching's definition.
        "connected": screening == "connected"
        and ((((memo.get("extraction") or {}).get("intelligence") or {}).get("call") or {}).get("reached_conversation") is not False),
        # The rep's declaration (after-call outcome, accepted proposal, CRM stage), never the model's reading.
        "meeting_agreed": memo.get("rep_outcome") == "meeting_booked",
    }


def _memos_in_period(memos: list[dict], period_start: datetime, period_end: datetime) -> list[dict]:
    start_s = period_start.isoformat()
    end_s = period_end.isoformat()
    kept: list[dict] = []
    for memo in memos:
        captured = _parse_iso(memo.get("capture_started_at") or memo.get("created_at"))
        if captured is None or captured < start_s or captured >= end_s:
            continue
        kept.append(memo)
    return kept


def _outcomes_for_snapshot(observations: list[dict] | None, *, user_id: str) -> dict:
    if observations is None:
        return {"coverage": "unavailable"}
    from app.services.team_insights.outcomes import adherence_crm_outcomes

    crm = adherence_crm_outcomes(observations, user_id=user_id)
    if crm.get("crm_coverage") == "complete":
        return {
            "coverage": "complete",
            "won": crm.get("won") or 0,
            "lost": crm.get("lost") or 0,
        }
    return {"coverage": crm.get("crm_coverage") or "unavailable"}


def _load_recent_memos_for_tick(supabase, since_iso: str) -> list[dict]:
    """Load memos that might fall in a local day window (row or capture time since *since*)."""
    columns = "id,company_id,user_id,screening_outcome,extraction,capture_started_at,created_at,hubspot_contact_id,hubspot_deal_id"
    by_id: dict[str, dict] = {}
    for column in ("created_at", "capture_started_at"):
        try:
            result = _with_outcome(lambda cols: supabase.table("memos").select(cols).gte(column, since_iso).execute(), columns)
        except Exception:
            logger.exception("daily report tick: list recent memos failed (%s)", column)
            continue
        for row in result.data or []:
            memo_id = row.get("id")
            if memo_id is not None:
                by_id[str(memo_id)] = row
    from app.services.coaching.crm_meetings import apply_rep_meetings

    return apply_rep_meetings(supabase, list(by_id.values()))


def _with_outcome(run, columns: str):
    """The query with rep_outcome (migration 062) when the column exists, without it otherwise."""
    try:
        return run(columns + ",rep_outcome")
    except Exception:
        return run(columns)


def _load_memos_for_user(supabase, *, company_id: str, user_id: str) -> list[dict]:
    try:
        result = _with_outcome(
            lambda cols: supabase.table("memos").select(cols).eq("company_id", company_id).eq("user_id", user_id).execute(),
            "id,user_id,company_id,source,source_type,interaction_kind,"
            "screening_outcome,extraction,capture_started_at,created_at,"
            "sales_motion_key,followup,hubspot_contact_id,hubspot_deal_id",
        )
        from app.services.coaching.crm_meetings import apply_rep_meetings

        return apply_rep_meetings(supabase, list(result.data or []))
    except Exception:
        logger.exception("daily report: load memos failed")
        return []


def _meetings_held(period_memos: list[dict]) -> int:
    """T12 AE card "reuniones hechas": captured interactions that were a meeting or visit,
    not a call - independent of whether a meeting was ever agreed."""
    return sum(1 for memo in period_memos if memo.get("interaction_kind") in _MEETING_KINDS)


def _proposals_sent(period_memos: list[dict]) -> int:
    """T12 AE card "propuestas enviadas": follow-ups sent (D9, any channel, T8's vocify_email
    included) on the closing flow - the AE's proposal, not the SDR's invitation."""
    count = 0
    for memo in period_memos:
        if memo.get("sales_motion_key") != "closing":
            continue
        followup = memo.get("followup") or {}
        if isinstance(followup, dict) and followup.get("status") == "sent":
            count += 1
    return count


def _handoffs_created(supabase, *, company_id: str, user_id: str, start_iso: str, end_iso: str) -> int | None:
    """T12 SDR card "traspasos": handoffs this SDR created in the period. A read failure
    (including migration 056 not applied yet) is unavailable, never a fabricated zero."""
    try:
        rows = (
            supabase.table("deal_handoffs")
            .select("id,created_at")
            .eq("company_id", company_id)
            .eq("sdr_user_id", user_id)
            .gte("created_at", start_iso)
            .execute()
        ).data or []
    except Exception:
        logger.exception("daily report: load handoffs failed")
        return None
    return sum(1 for row in rows if str(row.get("created_at") or "") < end_iso)


def _deals_in_progress(supabase, *, company_id: str, user_id: str) -> int | None:
    """Active handoffs into this AE right now - a gauge, not a period count. A read
    failure (including migration 056 not applied yet) is unavailable, same as `handoffs`
    below - never a fabricated zero, unlike active_handoffs_for_ae's own "no table yet"
    fallback (that one feeds Hoy, where an empty list and "unavailable" look the same)."""
    try:
        rows = (
            supabase.table("deal_handoffs")
            .select("id")
            .eq("company_id", company_id)
            .eq("ae_user_id", user_id)
            .eq("status", "active")
            .execute()
        ).data or []
    except Exception:
        logger.exception("daily report: load deals in progress failed")
        return None
    return len(rows)


def _flow_facts(
    supabase, *, company_id: str, user_id: str, period_memos: list[dict], start_iso: str, end_iso: str,
) -> dict:
    deals_in_progress = _deals_in_progress(supabase, company_id=company_id, user_id=user_id)
    return {
        "handoffs": _handoffs_created(supabase, company_id=company_id, user_id=user_id, start_iso=start_iso, end_iso=end_iso),
        "meetings_held": _meetings_held(period_memos),
        "deals_in_progress": deals_in_progress,
        "proposals_sent": _proposals_sent(period_memos),
    }


def _load_outcome_observations(supabase, company_id: str) -> list[dict] | None:
    try:
        result = (
            supabase.table("team_outcome_observations")
            .select("connection_id,deal_id,status,owner_user_id,attribution,observed_at")
            .eq("company_id", company_id)
            .execute()
        )
        return list(result.data or [])
    except Exception:
        return None


def _existing_report_id(
    supabase,
    *,
    company_id: str,
    user_id: str,
    period_start_iso: str,
) -> str | None:
    try:
        stored = (
            supabase.table("reports")
            .select("id")
            .eq("company_id", company_id)
            .eq("user_id", user_id)
            .eq("scope", "self")
            .eq("period_start", period_start_iso)
            .eq("report_type", "daily")
            .limit(1)
            .execute()
        )
        rows = stored.data or []
        if rows:
            return str(rows[0]["id"])
    except Exception:
        logger.exception("daily report: load existing report failed")
    return None


def _ensure_report_notification(supabase, *, report_id: str, user_id: str) -> None:
    try:
        stored = (
            supabase.table("report_notifications")
            .select("id")
            .eq("user_id", user_id)
            .eq("report_id", report_id)
            .limit(1)
            .execute()
        )
        if stored.data:
            return
        supabase.table("report_notifications").insert(
            {
                "id": str(uuid.uuid4()),
                "report_id": report_id,
                "user_id": user_id,
                "read_at": None,
            }
        ).execute()
    except Exception:
        logger.exception("daily report: ensure notification failed")


def ensure_self_daily_report(
    supabase,
    *,
    company_id: str,
    user_id: str,
    timezone: str,
    now: datetime,
) -> str | None:
    """Upsert one self daily report for the user's local day when they have memos in period."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    period_start, period_end = period_bounds(now, timezone)
    period_start_iso = period_start.isoformat()
    period_end_iso = period_end.isoformat()
    memos = _load_memos_for_user(supabase, company_id=company_id, user_id=user_id)
    period_memos = _memos_in_period(memos, period_start, period_end)
    if not period_memos:
        return None
    interactions = [row for memo in period_memos if (row := _interaction_from_memo(memo)) is not None]
    observations = _load_outcome_observations(supabase, company_id)
    outcomes = _outcomes_for_snapshot(observations, user_id=user_id)
    sales_role = None
    flow_facts = None
    if is_enabled(supabase, company_id, FLOW_FLAG):
        sales_role = sales_role_for_user(supabase, user_id, company_id=company_id) or "general"
        flow_facts = _flow_facts(
            supabase,
            company_id=company_id,
            user_id=user_id,
            period_memos=period_memos,
            start_iso=period_start_iso,
            end_iso=period_end_iso,
        )
    snapshot = build_snapshot(
        scope="self",
        period_start=period_start_iso,
        period_end=period_end_iso,
        timezone=timezone,
        interactions=interactions,
        outcomes=outcomes,
        adherence_parts=None,
        channels=interaction_channels(period_memos, start=period_start, end=period_end),
        sales_role=sales_role,
        flow_facts=flow_facts,
    )
    # Look the report up before the coaching line: that read set is the expensive part.
    report_id = _existing_report_id(
        supabase,
        company_id=company_id,
        user_id=user_id,
        period_start_iso=period_start_iso,
    ) or str(uuid.uuid4())
    snapshot["coaching"] = self_daily_coaching(
        supabase, company_id=company_id, user_id=user_id, period_start=period_start, period_end=period_end
    )
    payload = {
        "id": report_id,
        "company_id": company_id,
        "user_id": user_id,
        "scope": "self",
        "period_start": period_start_iso,
        "report_type": "daily",
        "revision": 1,
        "snapshot": snapshot,
    }
    supabase.table("reports").upsert(
        payload,
        on_conflict="company_id,user_id,scope,period_start,report_type",
    ).execute()
    _ensure_report_notification(supabase, report_id=report_id, user_id=user_id)
    return report_id


def ensure_self_daily_reports_for_due_tick(supabase, now: datetime) -> None:
    """Ensure daily rows for users with memos in their local day before the email tick loads people."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    since = (now - timedelta(days=2)).isoformat()
    memos = _load_recent_memos_for_tick(supabase, since)
    if not memos:
        return
    user_ids = list({str(m["user_id"]) for m in memos if m.get("user_id")})
    tz_by_user: dict[str, str] = {}
    if user_ids:
        try:
            prefs = (
                supabase.table("brief_preferences")
                .select("user_id,timezone")
                .in_("user_id", user_ids)
                .execute()
            )
            for row in prefs.data or []:
                tz_by_user[str(row["user_id"])] = row.get("timezone") or MADRID
        except Exception:
            logger.exception("daily report tick: load timezones failed")
    report_prefs = load_preference_rows(supabase, user_ids)
    seen: set[tuple[str, str]] = set()
    for memo in memos:
        company_id = str(memo.get("company_id") or "").strip()
        user_id = str(memo.get("user_id") or "").strip()
        if not company_id or not user_id or not is_opted_in(report_prefs, user_id, "daily"):
            continue
        key = (company_id, user_id)
        if key in seen:
            continue
        tz_name = tz_by_user.get(user_id, MADRID)
        period_start, period_end = period_bounds(now, tz_name)
        if not _memos_in_period([memo], period_start, period_end):
            continue
        seen.add(key)
        ensure_self_daily_report(
            supabase,
            company_id=company_id,
            user_id=user_id,
            timezone=tz_name,
            now=now,
        )
