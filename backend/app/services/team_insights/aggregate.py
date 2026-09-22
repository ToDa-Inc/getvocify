"""Team metrics. Members get nothing. Adherence is the sum of counts, not the average of rates."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.services.coaching.metrics import aggregate_adherence

_MADRID = ZoneInfo("Europe/Madrid")

_TEAM_ROLES = frozenset({"owner", "admin"})
_SCREENING_ATTEMPTS = frozenset({"voicemail", "no_response", "connected"})


class TeamAccessError(Exception):
    pass


def assert_team_reader(role: str) -> None:
    if role not in _TEAM_ROLES:
        raise TeamAccessError("equipo denegado")


def authorized_scope(*, role: str, requested_user_id: str | None, instruction: str) -> dict:
    """Free text never widens the scope. The role is the server's."""
    del instruction
    assert_team_reader(role)
    if requested_user_id:
        return {"scope": "user", "user_id": requested_user_id}
    return {"scope": "team", "user_id": None}


def madrid_week_bounds(*, now: datetime | None = None) -> tuple[datetime, datetime]:
    """Current ISO week in Europe/Madrid as UTC half-open [start, end)."""
    instant = now or datetime.now(timezone.utc)
    local = instant.astimezone(_MADRID)
    monday_local = (local.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=local.weekday()))
    next_monday_local = monday_local + timedelta(days=7)
    return monday_local.astimezone(timezone.utc), next_monday_local.astimezone(timezone.utc)


def _parse_instant(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        dt = datetime.fromisoformat(text)
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def activity_counts(rows: list[dict], *, start: datetime, end: datetime) -> dict:
    """Voicemail and no-answer are attempts only. Connected is an attempt and a conversation."""
    attempts = 0
    connected = 0
    meetings = 0
    for row in rows:
        observed = _parse_instant(row.get("observed_at"))
        if observed is None or observed < start or observed >= end:
            continue
        screening = row.get("screening")
        if screening in _SCREENING_ATTEMPTS:
            attempts += 1
            if screening == "connected":
                connected += 1
        if row.get("meeting_agreed") is True:
            meetings += 1
    return {"attempts": attempts, "connected": connected, "meetings": meetings}


def activity_row_from_memo(memo: dict) -> dict | None:
    screening = memo.get("screening_outcome")
    if screening not in _SCREENING_ATTEMPTS:
        return None
    intel = memo.get("intelligence") or (memo.get("extraction") or {}).get("intelligence") or {}
    meeting = intel.get("meeting") if isinstance(intel, dict) else {}
    agreed = meeting.get("agreed") if isinstance(meeting, dict) else None
    observed = memo.get("observed_at") or memo.get("capture_started_at") or memo.get("created_at")
    return {"screening": screening, "meeting_agreed": agreed is True, "observed_at": observed}


def adherence_part_from_score(score: dict) -> dict | None:
    if score.get("status") not in {"ready", "partial"}:
        return None
    return {
        "met_steps": int(score.get("met_steps") or 0),
        "missed_steps": int(score.get("missed_steps") or 0),
        "unknown_steps": int(score.get("unknown_steps") or 0),
        "not_applicable_steps": int(score.get("not_applicable_steps") or 0),
    }


def load_team_adherence_inputs(supabase, company_id: str) -> dict:
    """Memos and scores for the company. Empty lists when the read fails."""
    activity_rows: list[dict] = []
    parts: list[dict] = []
    playbook_present = False
    try:
        memos = (
            supabase.table("memos")
            .select("id,screening_outcome,extraction,intelligence,capture_started_at,created_at")
            .eq("company_id", company_id)
            .execute()
        )
        memo_ids: list[str] = []
        for memo in memos.data or []:
            memo_ids.append(str(memo.get("id")))
            row = activity_row_from_memo(memo)
            if row is not None:
                activity_rows.append(row)
        if memo_ids:
            scores = supabase.table("memo_scores").select("memo_id,score").in_("memo_id", memo_ids).execute()
            for item in scores.data or []:
                score = item.get("score") or {}
                part = adherence_part_from_score(score if isinstance(score, dict) else {})
                if part is not None:
                    parts.append(part)
        published = (
            supabase.table("playbooks")
            .select("id, playbook_versions!inner(status)")
            .eq("company_id", company_id)
            .eq("playbook_versions.status", "published")
            .limit(1)
            .execute()
        )
        playbook_present = bool(published.data)
    except Exception:
        pass
    period_start, period_end = madrid_week_bounds()
    return {
        "parts": parts,
        "playbook_present": playbook_present,
        "sample_size": len(parts),
        "activity_rows": activity_rows,
        "activity_period_start": period_start,
        "activity_period_end": period_end,
    }


def team_adherence(
    *,
    role: str,
    parts: list[dict],
    playbook_present: bool,
    sample_size: int,
    activity_rows: list[dict] | None = None,
    activity_period_start: datetime | None = None,
    activity_period_end: datetime | None = None,
) -> dict:
    assert_team_reader(role)
    if activity_rows is not None:
        if activity_period_start is None or activity_period_end is None:
            activity_period_start, activity_period_end = madrid_week_bounds()
        activity = activity_counts(
            activity_rows,
            start=activity_period_start,
            end=activity_period_end,
        )
    else:
        activity = {}
    if not playbook_present or sample_size < 1:
        body = {
            "met_steps": 0,
            "applicable_steps": 0,
            "unknown_steps": 0,
            "adherence": None,
            "coverage": None,
            "conclusion": None,
        }
        body.update(activity)
        return body
    metrics = aggregate_adherence(parts)
    conclusion = None
    if sample_size < 5:
        conclusion = None
    body = {
        "met_steps": metrics["met_steps"],
        "applicable_steps": metrics["applicable_steps"],
        "unknown_steps": metrics["unknown_steps"],
        "adherence": metrics["adherence"],
        "coverage": metrics["coverage"],
        "conclusion": conclusion,
    }
    body.update(activity)
    return body
