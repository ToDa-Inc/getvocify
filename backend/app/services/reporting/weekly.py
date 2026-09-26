"""Weekly snapshots over the local working week. A day not yet observed is a gap, not a zero."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.services.reporting.aggregate import build_snapshot
from app.services.reporting.channels import interaction_channels
from app.services.reporting.daily_snapshot import _interaction_from_memo
from app.services.team_insights.aggregate import activity_counts, activity_row_from_memo
from app.services.team_insights.objections import objection_counts

WEEKLY_DUE_WEEKDAY = 4
WEEKLY_DUE_HOUR = 18
WORKING_DAYS = 5
MAX_OBJECTIONS = 3


def _aware(now: datetime) -> datetime:
    return now if now.tzinfo else now.replace(tzinfo=timezone.utc)


def _local_monday(now: datetime, tz_name: str) -> datetime:
    local = _aware(now).astimezone(ZoneInfo(tz_name))
    return (local - timedelta(days=local.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)


def week_bounds(now: datetime, tz_name: str) -> tuple[datetime, datetime]:
    """[Monday 00:00, Saturday 00:00) local, as UTC. Weekend ticks belong to the week just worked."""
    monday = _local_monday(now, tz_name)
    saturday = monday + timedelta(days=WORKING_DAYS)
    return monday.astimezone(timezone.utc), saturday.astimezone(timezone.utc)


def weekly_due(now: datetime, tz_name: str) -> bool:
    """From Friday 18:00 local until the next Monday, so a missed Friday is caught on the weekend."""
    monday = _local_monday(now, tz_name)
    due_from = monday + timedelta(days=WEEKLY_DUE_WEEKDAY, hours=WEEKLY_DUE_HOUR)
    return due_from <= _aware(now) < monday + timedelta(days=7)


def weekly_due_somewhere(now: datetime) -> bool:
    """The due windows of UTC+14 and UTC-12 overlap, so together they cover every zone in between."""
    return weekly_due(now, "Etc/GMT-14") or weekly_due(now, "Etc/GMT+12")


def day_series(
    rows: list[dict],
    *,
    start: datetime,
    end: datetime,
    tz_name: str,
    generated_at: datetime,
) -> list[dict]:
    """Per local day: connected calls and meetings. Days starting after generation are not covered."""
    generated = _aware(generated_at)
    series: list[dict] = []
    day = start.astimezone(ZoneInfo(tz_name))
    while day < end:
        next_day = day + timedelta(days=1)
        if day > generated:
            series.append({
                "date": day.date().isoformat(),
                "connected_calls": None,
                "meetings_agreed": None,
                "covered": False,
            })
        else:
            counts = activity_counts(rows, start=day.astimezone(timezone.utc), end=next_day.astimezone(timezone.utc))
            series.append({
                "date": day.date().isoformat(),
                "connected_calls": counts["connected"],
                "meetings_agreed": counts["meetings"],
                "covered": True,
            })
        day = next_day
    return series


def _objections(pattern_rows: list[dict] | None, *, start: datetime, end: datetime) -> list[dict] | None:
    if pattern_rows is None:
        return None
    return objection_counts(pattern_rows, start=start, end=end)[:MAX_OBJECTIONS]


def weekly_self_snapshot(
    *,
    memos: list[dict],
    pattern_rows: list[dict] | None,
    period_start: datetime,
    period_end: datetime,
    timezone: str,
    generated_at: datetime,
    outcomes: dict,
) -> dict:
    """Same aggregator as the daily report, plus the daily series and the most frequent objections."""
    interactions = [row for memo in memos if (row := _interaction_from_memo(memo)) is not None]
    snapshot = build_snapshot(
        scope="self",
        period_start=period_start.isoformat(),
        period_end=period_end.isoformat(),
        timezone=timezone,
        interactions=interactions,
        outcomes=outcomes,
        adherence_parts=None,
        channels=interaction_channels(memos, start=period_start, end=period_end),
    )
    activity = [row for memo in memos if (row := activity_row_from_memo(memo)) is not None]
    objections = _objections(pattern_rows, start=period_start, end=period_end)
    snapshot["report_type"] = "weekly"
    snapshot["generated_at"] = _aware(generated_at).isoformat()
    snapshot["series"] = day_series(
        activity, start=period_start, end=period_end, tz_name=timezone, generated_at=generated_at,
    )
    snapshot["objections"] = objections
    snapshot["coverage"]["objections"] = "unavailable" if objections is None else "complete"
    return snapshot


def _trend_cell(week: dict) -> dict:
    return {
        "state": week.get("state"),
        "met": int(week.get("met_steps") or 0),
        "applicable": int(week.get("applicable_steps") or 0),
        "sample_limited": bool(week.get("sample_limited")),
    }


def trend_block(trend: dict | None) -> dict | None:
    """Weekly adherence per rep for the team report: display names only, never user ids."""
    if not isinstance(trend, dict) or trend.get("coverage") != "complete" or not trend.get("team"):
        return None
    return {
        "weeks": [str(week.get("week_start")) for week in trend.get("weeks") or []],
        "team": [_trend_cell(week) for week in trend["team"].get("weeks") or []],
        "reps": [
            {"name": rep.get("name") or "", "weeks": [_trend_cell(week) for week in rep.get("weeks") or []]}
            for rep in trend.get("reps") or []
        ],
    }


def team_snapshot(
    *,
    team_body: dict,
    series: list[dict],
    period_start: datetime,
    period_end: datetime,
    timezone: str,
    generated_at: datetime,
    channels: dict[str, int] | None = None,
) -> dict:
    """C18 shape from the team panel aggregate. No per-rep numbers, names or example conversations."""
    adherence = team_body.get("adherence")
    steps = (
        {"met": int(team_body.get("met_steps") or 0), "applicable": int(team_body.get("applicable_steps") or 0)}
        if adherence is not None
        else None
    )
    metrics = {
        "attempts": int(team_body.get("attempts") or 0),
        "connected_calls": int(team_body.get("connected") or 0),
        "meetings_agreed": int(team_body.get("meetings") or 0),
        # The panel's CRM read is not scoped to a period, so a weekly close count is not available.
        "deals_won": None,
        "deals_lost": None,
        "adherence": adherence,
    }
    if channels is not None:
        metrics["channels"] = dict(channels)
    return {
        "scope": "team",
        "report_type": "weekly",
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "timezone": timezone,
        "generated_at": _aware(generated_at).isoformat(),
        "metrics": metrics,
        "adherence_steps": steps,
        "sample_limited": bool(team_body.get("sample_limited")),
        "coverage": {"crm_outcomes": "unavailable", "objections": "complete"},
        "series": series,
        "objections": list(team_body.get("objection_categories") or [])[:MAX_OBJECTIONS],
        "examples": [],
        "coaching": None,
    }
