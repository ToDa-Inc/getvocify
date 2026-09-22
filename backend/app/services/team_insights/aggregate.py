"""Team metrics. Members get nothing. Adherence is the sum of counts, not the average of rates."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.services.activity_scope import author_display_name
from app.services.coaching.metrics import aggregate_adherence
from app.services.company import CompanyService
from app.services.team_insights.objections import objection_counts
from app.services.team_insights.outcomes import adherence_crm_outcomes

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


def adherence_parts_in_period(parts: list[dict], *, start: datetime, end: datetime) -> list[dict]:
    """Only scores whose observed_at falls in [start, end) feed team adherence."""
    kept: list[dict] = []
    for part in parts:
        observed = _parse_instant(part.get("observed_at"))
        if observed is None or observed < start or observed >= end:
            continue
        kept.append(part)
    return kept


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


def adherence_part_from_score(score: dict, *, observed_at=None) -> dict | None:
    if score.get("status") not in {"ready", "partial"}:
        return None
    part = {
        "met_steps": int(score.get("met_steps") or 0),
        "missed_steps": int(score.get("missed_steps") or 0),
        "unknown_steps": int(score.get("unknown_steps") or 0),
        "not_applicable_steps": int(score.get("not_applicable_steps") or 0),
    }
    instant = observed_at if observed_at is not None else score.get("observed_at")
    if instant is not None:
        part["observed_at"] = instant
    return part


def sort_reps_by_name(reps: list[dict]) -> list[dict]:
    """Alphabetical by display name (Spanish locale when available)."""
    import locale

    collator = locale.strxfrm
    try:
        locale.setlocale(locale.LC_COLLATE, "es_ES.UTF-8")
    except locale.Error:
        try:
            locale.setlocale(locale.LC_COLLATE, "es_ES")
        except locale.Error:
            collator = lambda text: (text or "").casefold()  # noqa: E731
    try:
        return sorted(reps, key=lambda rep: collator(str(rep.get("name") or "")))
    except Exception:
        return sorted(reps, key=lambda rep: str(rep.get("name") or "").casefold())


def load_team_reps(supabase, company_id: str) -> list[dict]:
    """Active company members as {userId, name}; never invent non-members."""
    try:
        members = CompanyService(supabase).list_members(company_id)
    except Exception:
        return []
    reps: list[dict] = []
    for member in members:
        if (member.get("status") or "active") != "active":
            continue
        uid = str(member.get("user_id") or "").strip()
        if not uid:
            continue
        reps.append(
            {
                "userId": uid,
                "name": author_display_name(member.get("full_name"), member.get("email")),
            }
        )
    return sort_reps_by_name(reps)


def load_team_adherence_inputs(
    supabase,
    company_id: str,
    *,
    user_id: str | None = None,
    motion: str | None = None,
) -> dict:
    """Memos and scores for the company. Empty lists when the read fails."""
    activity_rows: list[dict] = []
    parts: list[dict] = []
    pattern_rows: list[dict] = []
    playbook_present = False
    reps = load_team_reps(supabase, company_id)
    filter_user = (user_id or "").strip() or None
    filter_motion = (motion or "").strip() or None
    try:
        query = (
            supabase.table("memos")
            .select(
                "id,user_id,sales_motion_key,screening_outcome,extraction,intelligence,"
                "capture_started_at,created_at"
            )
            .eq("company_id", company_id)
        )
        if filter_user:
            query = query.eq("user_id", filter_user)
        if filter_motion:
            query = query.eq("sales_motion_key", filter_motion)
        memos = query.execute()
        memo_ids: list[str] = []
        for memo in memos.data or []:
            memo_ids.append(str(memo.get("id")))
            row = activity_row_from_memo(memo)
            if row is not None:
                activity_rows.append(row)
        if memo_ids:
            scores = (
                supabase.table("memo_scores")
                .select("memo_id,score,created_at")
                .in_("memo_id", memo_ids)
                .execute()
            )
            for item in scores.data or []:
                score = item.get("score") or {}
                part = adherence_part_from_score(
                    score if isinstance(score, dict) else {},
                    observed_at=item.get("created_at"),
                )
                if part is not None:
                    parts.append(part)
            patterns = (
                supabase.table("interaction_patterns")
                .select("category,kind,resolution,superseded,created_at")
                .in_("memo_id", memo_ids)
                .execute()
            )
            pattern_rows = list(patterns.data or [])
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
    outcome_observations: list[dict] | None = None
    try:
        observations = (
            supabase.table("team_outcome_observations")
            .select("connection_id,deal_id,status,owner_user_id,attribution,observed_at")
            .eq("company_id", company_id)
            .execute()
        )
        outcome_observations = list(observations.data or [])
    except Exception:
        outcome_observations = None
    period_start, period_end = madrid_week_bounds()
    return {
        "parts": parts,
        "playbook_present": playbook_present,
        "sample_size": len(parts),
        "activity_rows": activity_rows,
        "activity_period_start": period_start,
        "activity_period_end": period_end,
        "pattern_rows": pattern_rows,
        "reps": reps,
        "outcome_observations": outcome_observations,
        "outcome_user_id": filter_user,
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
    pattern_rows: list[dict] | None = None,
    reps: list[dict] | None = None,
    outcome_observations: list[dict] | None = None,
    outcome_user_id: str | None = None,
) -> dict:
    assert_team_reader(role)

    def with_crm_outcomes(body: dict) -> dict:
        if outcome_observations is None:
            body["crm_coverage"] = "unavailable"
            body["won"] = None
            body["lost"] = None
            body["unresolved_wins"] = 0
        else:
            body.update(adherence_crm_outcomes(outcome_observations, user_id=outcome_user_id))
        return body
    if activity_period_start is None or activity_period_end is None:
        activity_period_start, activity_period_end = madrid_week_bounds()
    week_parts = adherence_parts_in_period(
        parts,
        start=activity_period_start,
        end=activity_period_end,
    )
    effective_sample = len(week_parts)
    if activity_rows is not None:
        activity = activity_counts(
            activity_rows,
            start=activity_period_start,
            end=activity_period_end,
        )
    else:
        activity = {}
    sample_limited = 1 <= effective_sample < 5
    if not playbook_present or effective_sample < 1:
        body = {
            "met_steps": 0,
            "applicable_steps": 0,
            "unknown_steps": 0,
            "adherence": None,
            "coverage": None,
            "conclusion": None,
            "sample_limited": False,
        }
        body.update(activity)
        body["objection_categories"] = objection_counts(
            pattern_rows or [],
            start=activity_period_start,
            end=activity_period_end,
        )
        body["reps"] = reps or []
        return with_crm_outcomes(body)
    metrics = aggregate_adherence(week_parts)
    conclusion = None
    if effective_sample < 5:
        conclusion = None
    body = {
        "met_steps": metrics["met_steps"],
        "applicable_steps": metrics["applicable_steps"],
        "unknown_steps": metrics["unknown_steps"],
        "adherence": metrics["adherence"],
        "coverage": metrics["coverage"],
        "conclusion": conclusion,
        "sample_limited": sample_limited,
    }
    body.update(activity)
    body["objection_categories"] = objection_counts(
        pattern_rows or [],
        start=activity_period_start,
        end=activity_period_end,
    )
    body["reps"] = reps or []
    return with_crm_outcomes(body)
