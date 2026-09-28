"""Team activity metrics for the Head of Sales dashboard.

One definition per metric, shared by every surface that shows it (dashboard,
future weekly email, coaching). See docs/features/HEAD_OF_SALES_DASHBOARD_PLAN.md §3.

Source today is the Vocify dialer (`outbound_calls`). Meetings, deals and quality
metrics arrive in later phases; until then they are reported as unavailable with
a reason instead of as zero.

Definitions
-----------
- call: one `outbound_calls` row placed in the period (by `created_at`).
- connected: `call_disposition == "connected"`. Rows from before migration 027
  have no disposition; for those `answered_at` set means connected, otherwise the
  outcome is unknown.
- useful conversation: a connected call whose recording lasts at least
  `useful_call_seconds` (workspace setting, default 60).
- connection rate: connected / calls.
- median: per-person median over the people shown who placed at least one call
  in the period, so an idle seat does not drag the reference down.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable, Optional

from supabase import Client

DEFAULT_USEFUL_CALL_SECONDS = 60
PERIOD_PRESETS = ("week", "month", "last_30", "quarter")
SALES_ROLE_FILTERS = ("all", "sdr", "ae")

_NO_ANSWER = frozenset({"no_response", "no_answer", "busy"})
_FAILED = frozenset({"failed", "canceled"})
_PAGE_SIZE = 1000


@dataclass(frozen=True)
class Period:
    start: datetime  # inclusive
    end: datetime  # exclusive

    def contains(self, ts: datetime) -> bool:
        return self.start <= ts < self.end


@dataclass
class ActivityStats:
    calls: int = 0
    connected: int = 0
    voicemail: int = 0
    no_answer: int = 0
    failed: int = 0
    unknown: int = 0
    useful: int = 0
    talk_seconds: int = 0

    @property
    def connection_rate(self) -> Optional[float]:
        return self.connected / self.calls if self.calls else None

    @property
    def useful_rate(self) -> Optional[float]:
        return self.useful / self.connected if self.connected else None

    def add(self, other: "ActivityStats") -> None:
        for name in ("calls", "connected", "voicemail", "no_answer", "failed", "unknown", "useful", "talk_seconds"):
            setattr(self, name, getattr(self, name) + getattr(other, name))

    def to_dict(self) -> dict:
        return {
            "calls": self.calls,
            "connected": self.connected,
            "voicemail": self.voicemail,
            "no_answer": self.no_answer,
            "failed": self.failed,
            "unknown": self.unknown,
            "useful": self.useful,
            "talk_seconds": self.talk_seconds,
            "connection_rate": self.connection_rate,
            "useful_rate": self.useful_rate,
        }


@dataclass
class WeekBucket:
    week_start: date
    stats: ActivityStats = field(default_factory=ActivityStats)


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _day_start(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=timezone.utc)


def _quarter_start(d: date) -> date:
    return date(d.year, 3 * ((d.month - 1) // 3) + 1, 1)


def _shift_months(d: date, months: int) -> date:
    index = d.year * 12 + (d.month - 1) + months
    return date(index // 12, index % 12 + 1, 1)


def resolve_periods(preset: str, now: datetime) -> tuple[Period, Period]:
    """Current period (up to now) and the comparable stretch before it.

    Calendar presets compare like with like: month-to-date on the 28th is
    compared with the 1st–28th of the previous month, not the 28 days before.
    """
    now = _utc(now)
    today = now.date()
    if preset == "week":
        start = today - timedelta(days=today.weekday())
        prev_start = start - timedelta(days=7)
    elif preset == "month":
        start = today.replace(day=1)
        prev_start = _shift_months(start, -1)
    elif preset == "quarter":
        start = _quarter_start(today)
        prev_start = _shift_months(start, -3)
    elif preset == "last_30":
        current = Period(now - timedelta(days=30), now)
        return current, Period(now - timedelta(days=60), current.start)
    else:
        raise ValueError(f"Unknown period preset: {preset}")

    current = Period(_day_start(start), now)
    elapsed = now - current.start
    prev_begin = _day_start(prev_start)
    # Never let the comparison window run into the current period (e.g. 31 → 30 day months).
    prev_end = min(prev_begin + elapsed, current.start)
    return current, Period(prev_begin, prev_end)


def parse_ts(raw: object) -> Optional[datetime]:
    if not raw:
        return None
    if isinstance(raw, datetime):
        return _utc(raw)
    text = str(raw).replace("Z", "+00:00")
    try:
        return _utc(datetime.fromisoformat(text))
    except ValueError:
        return None


def classify_call(row: dict) -> str:
    """connected | voicemail | no_answer | failed | unknown."""
    disposition = (row.get("call_disposition") or "").strip().lower()
    if disposition == "connected":
        return "connected"
    if disposition == "voicemail":
        return "voicemail"
    if disposition in _NO_ANSWER:
        return "no_answer"
    if disposition in _FAILED:
        return "failed"
    if not disposition and row.get("answered_at"):
        return "connected"
    return "unknown"


def stats_for_calls(rows: Iterable[dict], useful_call_seconds: int) -> ActivityStats:
    stats = ActivityStats()
    for row in rows:
        stats.calls += 1
        outcome = classify_call(row)
        setattr(stats, outcome, getattr(stats, outcome) + 1)
        if outcome == "connected":
            seconds = int(row.get("recording_duration") or 0)
            stats.talk_seconds += seconds
            if seconds >= useful_call_seconds:
                stats.useful += 1
    return stats


def median_of(values: list[float]) -> Optional[float]:
    return float(statistics.median(values)) if values else None


def team_median(people: list[ActivityStats]) -> dict:
    active = [p for p in people if p.calls > 0]
    rates = [p.connection_rate for p in active if p.connection_rate is not None]
    useful_rates = [p.useful_rate for p in active if p.useful_rate is not None]
    return {
        "people": len(active),
        "calls": median_of([p.calls for p in active]),
        "connected": median_of([p.connected for p in active]),
        "useful": median_of([p.useful for p in active]),
        "connection_rate": median_of(rates),
        "useful_rate": median_of(useful_rates),
    }


def weekly_trend(rows: Iterable[dict], period: Period, useful_call_seconds: int) -> list[dict]:
    """Calls per ISO week (Monday start) across the period, empty weeks included."""
    first = period.start.date() - timedelta(days=period.start.weekday())
    buckets: dict[date, list[dict]] = {}
    cursor = first
    while _day_start(cursor) < period.end:
        buckets[cursor] = []
        cursor += timedelta(days=7)
    for row in rows:
        ts = parse_ts(row.get("created_at"))
        if not ts or not period.contains(ts):
            continue
        week = ts.date() - timedelta(days=ts.weekday())
        buckets.setdefault(week, []).append(row)
    out = []
    for week in sorted(buckets):
        stats = stats_for_calls(buckets[week], useful_call_seconds)
        out.append(
            {
                "week_start": week.isoformat(),
                "calls": stats.calls,
                "connected": stats.connected,
                "useful": stats.useful,
            }
        )
    return out


def filter_members(members: list[dict], sales_role: str) -> list[dict]:
    active = [m for m in members if m.get("user_id") and (m.get("status") or "active") == "active"]
    if sales_role == "all":
        return active
    return [m for m in active if (m.get("sales_role") or "other") == sales_role]


def build_team_metrics(
    *,
    members: list[dict],
    calls: list[dict],
    current: Period,
    previous: Period,
    useful_call_seconds: int,
    sales_role: str = "all",
) -> dict:
    """Pure aggregation: members + raw call rows → dashboard payload."""
    shown = filter_members(members, sales_role)
    by_user: dict[str, tuple[list[dict], list[dict]]] = {str(m["user_id"]): ([], []) for m in shown}
    current_rows: list[dict] = []
    for row in calls:
        uid = str(row.get("user_id") or "")
        if uid not in by_user:
            continue
        ts = parse_ts(row.get("created_at"))
        if not ts:
            continue
        if current.contains(ts):
            by_user[uid][0].append(row)
            current_rows.append(row)
        elif previous.contains(ts):
            by_user[uid][1].append(row)

    team_now, team_before = ActivityStats(), ActivityStats()
    people_now: list[ActivityStats] = []
    member_rows = []
    for member in shown:
        uid = str(member["user_id"])
        now_rows, before_rows = by_user[uid]
        now_stats = stats_for_calls(now_rows, useful_call_seconds)
        before_stats = stats_for_calls(before_rows, useful_call_seconds)
        team_now.add(now_stats)
        team_before.add(before_stats)
        people_now.append(now_stats)
        member_rows.append(
            {
                "user_id": uid,
                "name": (member.get("full_name") or "").strip() or (member.get("email") or "").split("@")[0],
                "email": member.get("email") or "",
                "sales_role": member.get("sales_role") or "other",
                "started_on": member.get("started_on"),
                "current": now_stats.to_dict(),
                "previous": before_stats.to_dict(),
            }
        )

    member_rows.sort(key=lambda r: (-r["current"]["calls"], r["name"].lower()))
    return {
        "sales_role": sales_role,
        "period": {"start": current.start.isoformat(), "end": current.end.isoformat()},
        "previous_period": {"start": previous.start.isoformat(), "end": previous.end.isoformat()},
        "settings": {"useful_call_seconds": useful_call_seconds},
        "members": member_rows,
        "team": {
            "current": team_now.to_dict(),
            "previous": team_before.to_dict(),
            "median": team_median(people_now),
        },
        "trend": weekly_trend(current_rows, current, useful_call_seconds),
        "source": "vocify_dialer",
        "unavailable": [
            {
                "metric": "meetings",
                "reason": "Meetings booked and held arrive with meeting detection and the HubSpot sync.",
            },
            {
                "metric": "adherence",
                "reason": "Playbook adherence arrives once your sales process is defined and calls are scored.",
            },
        ],
    }


def fetch_calls(supabase: Client, user_ids: list[str], since: datetime, until: datetime) -> list[dict]:
    """All call rows for these users in [since, until), paged past PostgREST's row cap."""
    if not user_ids:
        return []
    rows: list[dict] = []
    offset = 0
    while True:
        page = (
            supabase.table("outbound_calls")
            .select("user_id,created_at,answered_at,call_disposition,recording_duration")
            .in_("user_id", user_ids)
            .gte("created_at", since.isoformat())
            .lt("created_at", until.isoformat())
            .order("created_at")
            .range(offset, offset + _PAGE_SIZE - 1)
            .execute()
            .data
        ) or []
        rows.extend(page)
        if len(page) < _PAGE_SIZE:
            return rows
        offset += _PAGE_SIZE


def useful_call_seconds_from(settings: Optional[dict]) -> int:
    raw = (settings or {}).get("useful_call_seconds")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_USEFUL_CALL_SECONDS
    return value if value > 0 else DEFAULT_USEFUL_CALL_SECONDS
