"""Weekly personal and team reports: created once per person, scope and week, then emailed with the durable key."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable

from app.config import settings
from app.services.feature_flags import is_enabled
from app.services.reporting.channels import interaction_channels, load_team_channel_memos
from app.services.reporting.daily_snapshot import (
    _load_memos_for_user,
    _load_outcome_observations,
    _load_recent_memos_for_tick,
    _memos_in_period,
    _outcomes_for_snapshot,
)
from app.services.reporting.delivery import deliver_report, persist_report_delivery
from app.services.reporting.due_sends import MADRID, _failed_retry_due
from app.services.reporting.preferences import TEAM_ROLES, is_opted_in, load_preference_rows
from app.services.reporting.presentation import email_html_for_snapshot, email_subject
from app.services.reporting.resend_sender import report_resend_sender
from app.services.reporting.weekly import (
    day_series,
    team_snapshot,
    trend_block,
    week_bounds,
    weekly_due,
    weekly_due_somewhere,
    weekly_self_snapshot,
)
from app.services.team_insights import adherence_trend as trend_service
from app.services.team_insights.aggregate import TeamAccessError, load_team_adherence_inputs, team_adherence

logger = logging.getLogger(__name__)

WEEKLY_FLAG = "REPORTING_WEEKLY_ENABLED"
TEAM_FLAG = "REPORTING_TEAM_ENABLED"
LOOKBACK_DAYS = 8
REPORT_KEY = "company_id,user_id,scope,period_start,report_type"

SenderFactory = Callable[[dict, str, str, str], object]
TeamInputsLoader = Callable[[object, str], dict]
TREND_WEEKS = 4
TrendLoader = Callable[..., dict]


def _team_trend(supabase, company_id: str, *, role: str, now: datetime, timezone: str,
                load_trend: TrendLoader | None) -> dict | None:
    """A failed trend read drops the block; the rest of the team report still goes out."""
    if not is_enabled(supabase, company_id, trend_service.FLAG):
        return None
    loader = load_trend or trend_service.adherence_trend
    try:
        return trend_block(loader(supabase, company_id, role=role, now=now, tz_name=timezone, weeks=TREND_WEEKS))
    except Exception:
        logger.warning("team report adherence trend failed", extra={"company_id": company_id}, exc_info=True)
        return None


def _aware(now: datetime) -> datetime:
    return now if now.tzinfo else now.replace(tzinfo=timezone.utc)


def _timezones(supabase, user_ids: list[str]) -> dict[str, str]:
    ids = sorted({str(uid) for uid in user_ids if uid})
    if not ids:
        return {}
    try:
        result = supabase.table("brief_preferences").select("user_id,timezone").in_("user_id", ids).execute()
    except Exception:
        logger.exception("weekly reports: load timezones failed")
        return {}
    return {str(row["user_id"]): row.get("timezone") or MADRID for row in (result.data or [])}


def active_role(supabase, company_id: str, user_id: str) -> str | None:
    """The role right now. A removed member has none."""
    try:
        rows = (
            supabase.table("company_members")
            .select("role,status")
            .eq("company_id", company_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        ).data or []
    except Exception:
        logger.exception("weekly reports: load role failed")
        return None
    if not rows or (rows[0].get("status") or "active") != "active":
        return None
    return rows[0].get("role")


def _find_report(supabase, *, company_id: str, user_id: str, scope: str, period_start: str) -> str | None:
    rows = (
        supabase.table("reports")
        .select("id")
        .eq("company_id", company_id)
        .eq("user_id", user_id)
        .eq("scope", scope)
        .eq("period_start", period_start)
        .eq("report_type", "weekly")
        .limit(1)
        .execute()
    ).data or []
    return str(rows[0]["id"]) if rows else None


def _create_once(supabase, *, company_id: str, user_id: str, scope: str, period_start: str, snapshot: dict) -> str | None:
    """Two workers race on the unique key; the loser keeps the winner's row and snapshot."""
    supabase.table("reports").upsert(
        {
            "id": str(uuid.uuid4()),
            "company_id": company_id,
            "user_id": user_id,
            "scope": scope,
            "period_start": period_start,
            "report_type": "weekly",
            "revision": 1,
            "snapshot": snapshot,
        },
        on_conflict=REPORT_KEY,
        ignore_duplicates=True,
    ).execute()
    return _find_report(supabase, company_id=company_id, user_id=user_id, scope=scope, period_start=period_start)


def _notify_once(supabase, *, report_id: str, user_id: str) -> None:
    supabase.table("report_notifications").upsert(
        {"id": f"n:{report_id}", "report_id": report_id, "user_id": user_id, "read_at": None},
        on_conflict="id",
        ignore_duplicates=True,
    ).execute()


def _load_patterns(supabase, memo_ids: list[str]) -> list[dict] | None:
    if not memo_ids:
        return []
    try:
        return (
            supabase.table("interaction_patterns")
            .select("category,kind,resolution,superseded,created_at")
            .in_("memo_id", memo_ids)
            .execute()
        ).data or []
    except Exception:
        logger.exception("weekly reports: load objections failed")
        return None


def ensure_self_weekly_report(supabase, *, company_id: str, user_id: str, timezone: str, now: datetime) -> str | None:
    now = _aware(now)
    if not weekly_due(now, timezone) or not is_enabled(supabase, company_id, WEEKLY_FLAG):
        return None
    if not is_opted_in(load_preference_rows(supabase, [user_id]), user_id, "weekly"):
        return None
    start, end = week_bounds(now, timezone)
    existing = _find_report(supabase, company_id=company_id, user_id=user_id, scope="self", period_start=start.isoformat())
    if existing:
        _notify_once(supabase, report_id=existing, user_id=user_id)
        return existing
    memos = _memos_in_period(_load_memos_for_user(supabase, company_id=company_id, user_id=user_id), start, end)
    if not memos:
        return None
    snapshot = weekly_self_snapshot(
        memos=memos,
        pattern_rows=_load_patterns(supabase, [str(memo["id"]) for memo in memos if memo.get("id")]),
        period_start=start,
        period_end=end,
        timezone=timezone,
        generated_at=now,
        outcomes=_outcomes_for_snapshot(_load_outcome_observations(supabase, company_id), user_id=user_id),
    )
    report_id = _create_once(
        supabase, company_id=company_id, user_id=user_id, scope="self", period_start=start.isoformat(), snapshot=snapshot,
    )
    if report_id:
        _notify_once(supabase, report_id=report_id, user_id=user_id)
    return report_id


def _team_has_activity(body: dict) -> bool:
    return bool(
        body.get("attempts") or body.get("meetings") or body.get("applicable_steps") or body.get("objection_categories")
    )


def _team_channels(supabase, company_id: str, inputs: dict, *, start: datetime, end: datetime) -> dict | None:
    member_ids = [str(rep["userId"]) for rep in inputs.get("reps") or [] if rep.get("userId")]
    memos = load_team_channel_memos(supabase, company_id, member_ids, start=start, end=end)
    return None if memos is None else interaction_channels(memos, start=start, end=end)


def ensure_team_weekly_report(
    supabase,
    *,
    company_id: str,
    user_id: str,
    timezone: str,
    now: datetime,
    load_inputs: TeamInputsLoader | None = None,
    load_trend: TrendLoader | None = None,
) -> str | None:
    """Only for an active owner/admin at generation time, from the team panel's own aggregate."""
    now = _aware(now)
    if not weekly_due(now, timezone) or not is_enabled(supabase, company_id, TEAM_FLAG):
        return None
    role = active_role(supabase, company_id, user_id)
    if role not in TEAM_ROLES:
        return None
    if not is_opted_in(load_preference_rows(supabase, [user_id]), user_id, "team"):
        return None
    start, end = week_bounds(now, timezone)
    existing = _find_report(supabase, company_id=company_id, user_id=user_id, scope="team", period_start=start.isoformat())
    if existing:
        _notify_once(supabase, report_id=existing, user_id=user_id)
        return existing
    loader = load_inputs or (lambda client, company: load_team_adherence_inputs(client, company))
    inputs = {**loader(supabase, company_id), "activity_period_start": start, "activity_period_end": end}
    try:
        body = team_adherence(role=role, **inputs)
    except TeamAccessError:
        return None
    channels = _team_channels(supabase, company_id, inputs, start=start, end=end)
    if not _team_has_activity(body) and not any((channels or {}).values()):
        return None
    snapshot = team_snapshot(
        team_body=body,
        series=day_series(inputs.get("activity_rows") or [], start=start, end=end, tz_name=timezone, generated_at=now),
        period_start=start,
        period_end=end,
        timezone=timezone,
        generated_at=now,
        channels=channels,
    )
    trend = _team_trend(supabase, company_id, role=role, now=now, timezone=timezone, load_trend=load_trend)
    if trend:
        snapshot["adherence_trend"] = trend
    report_id = _create_once(
        supabase, company_id=company_id, user_id=user_id, scope="team", period_start=start.isoformat(), snapshot=snapshot,
    )
    if report_id:
        _notify_once(supabase, report_id=report_id, user_id=user_id)
    return report_id


def _team_recipients(supabase, company_id: str) -> list[str]:
    try:
        rows = (
            supabase.table("company_members")
            .select("user_id,role,status")
            .eq("company_id", company_id)
            .execute()
        ).data or []
    except Exception:
        logger.exception("weekly reports: load members failed")
        return []
    return [
        str(row["user_id"])
        for row in rows
        if row.get("user_id") and row.get("role") in TEAM_ROLES and (row.get("status") or "active") == "active"
    ]


def ensure_weekly_reports_for_tick(
    supabase,
    now: datetime,
    *,
    load_team_inputs: TeamInputsLoader | None = None,
) -> None:
    """People and companies with conversations in the last days. Each report is checked on its own."""
    now = _aware(now)
    if not weekly_due_somewhere(now):
        return
    memos = _load_recent_memos_for_tick(supabase, (now - timedelta(days=LOOKBACK_DAYS)).isoformat())
    pairs = sorted({
        (str(memo["company_id"]), str(memo["user_id"]))
        for memo in memos
        if memo.get("company_id") and memo.get("user_id")
    })
    companies = sorted({company for company, _ in pairs})
    team_by_company = {
        company: _team_recipients(supabase, company) if is_enabled(supabase, company, TEAM_FLAG) else []
        for company in companies
    }
    tz_by_user = _timezones(supabase, [uid for _, uid in pairs] + [uid for ids in team_by_company.values() for uid in ids])
    for company_id, user_id in pairs:
        try:
            ensure_self_weekly_report(
                supabase, company_id=company_id, user_id=user_id, timezone=tz_by_user.get(user_id, MADRID), now=now,
            )
        except Exception:
            logger.exception("weekly reports: self report failed")
    for company_id, recipients in team_by_company.items():
        for user_id in recipients:
            try:
                ensure_team_weekly_report(
                    supabase,
                    company_id=company_id,
                    user_id=user_id,
                    timezone=tz_by_user.get(user_id, MADRID),
                    now=now,
                    load_inputs=load_team_inputs,
                )
            except Exception:
                logger.exception("weekly reports: team report failed")


def _emails_for(supabase, user_ids: list[str]) -> dict[str, str]:
    from app.services.reporting.tick_bindings import _emails_for_user_ids

    return _emails_for_user_ids(supabase, user_ids)


def _may_receive(supabase, report: dict, prefs: dict[str, dict]) -> bool:
    """Flag, preference and role re-read right before sending."""
    company_id = str(report["company_id"])
    user_id = str(report["user_id"])
    team = report.get("scope") == "team"
    if not is_enabled(supabase, company_id, TEAM_FLAG if team else WEEKLY_FLAG):
        return False
    if not is_opted_in(prefs, user_id, "team" if team else "weekly"):
        return False
    role = active_role(supabase, company_id, user_id)
    return role in TEAM_ROLES if team else role is not None


def _send_due(prior: dict | None, now: datetime, tz_name: str) -> bool:
    if prior is None:
        return True
    status = prior.get("delivery_status")
    if status in ("sent", "uncertain"):
        return False
    if status == "failed":
        return _failed_retry_due(now, tz_name, prior)
    return True


def deliver_weekly_reports_for_tick(supabase, now: datetime, *, sender_factory: SenderFactory | None) -> None:
    if sender_factory is None:
        return
    now = _aware(now)
    since = (now - timedelta(days=LOOKBACK_DAYS)).isoformat()
    reports = (
        supabase.table("reports")
        .select("id,company_id,user_id,scope,period_start,report_type,revision,snapshot")
        .eq("report_type", "weekly")
        .gte("period_start", since)
        .execute()
    ).data or []
    if not reports:
        return
    deliveries = (
        supabase.table("report_deliveries")
        .select("idempotency_key,report_id,delivery_status,channel,created_at")
        .in_("report_id", [str(report["id"]) for report in reports])
        .eq("channel", "email")
        .execute()
    ).data or []
    by_key = {row["idempotency_key"]: row for row in deliveries}
    user_ids = [str(report["user_id"]) for report in reports]
    prefs = load_preference_rows(supabase, user_ids)
    tz_by_user = _timezones(supabase, user_ids)
    emails = _emails_for(supabase, user_ids)
    for report in reports:
        report_id = str(report["id"])
        revision = int(report.get("revision") or 1)
        user_id = str(report["user_id"])
        prior = by_key.get(f"{report_id}:r{revision}:email")
        if not _send_due(prior, now, tz_by_user.get(user_id, MADRID)):
            continue
        email = (emails.get(user_id) or "").strip()
        if not email or not _may_receive(supabase, report, prefs):
            continue
        snapshot = report.get("snapshot") or {}
        sender = sender_factory(report, email, email_subject(snapshot), email_html_for_snapshot(snapshot, report_id=report_id))
        if sender is None:
            continue
        result = deliver_report(
            report={"id": report_id, "revision": revision}, channel="email", existing=prior, sender=sender, allowed=True,
        )
        if result.get("delivery_status") in ("sent", "failed", "uncertain"):
            persist_report_delivery(
                supabase,
                idempotency_key=result["idempotency_key"],
                report_id=report_id,
                channel="email",
                delivery_status=result["delivery_status"],
                attempt_at=now,
            )


def resend_sender_factory() -> SenderFactory | None:
    """No Resend key: no sender, nothing recorded as sent."""
    if not (settings.RESEND_API_KEY or "").strip():
        return None
    from app.integrations.resend_client import ResendClient

    client = ResendClient()
    return lambda _report, email, subject, html: report_resend_sender(client, to=email, subject=subject, html=html)


def tick_weekly_reports(supabase, now: datetime) -> None:
    ensure_weekly_reports_for_tick(supabase, now)
    deliver_weekly_reports_for_tick(supabase, now, sender_factory=resend_sender_factory())
