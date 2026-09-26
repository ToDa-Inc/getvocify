"""Weekly playbook adherence per rep. A week without conversations is a gap, not a zero.

Counts are summed and passed through the F09 formula; rates are never averaged. The CRM
outcome is not read: this measures process, not result.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.services.coaching.metrics import aggregate_adherence
from app.services.team_insights.aggregate import _parse_instant, assert_team_reader, load_team_reps

FLAG = "TEAM_ADHERENCE_TREND_ENABLED"
DEFAULT_WEEKS = 8
MAX_WEEKS = 12
DEFAULT_TZ = "Europe/Madrid"

_NOT_CONVERSATIONS = frozenset({"voicemail", "no_response"})
_SCORED = frozenset({"ready", "partial"})
_MEMO_PAGE = 1000
_SCORE_BATCH = 200
_SAMPLE_LIMIT = 5
_COUNT_KEYS = ("met_steps", "missed_steps", "unknown_steps", "not_applicable_steps")


def week_starts(*, now: datetime, weeks: int, tz_name: str = DEFAULT_TZ) -> list[date]:
    """Local Mondays, oldest first, ending with the current week."""
    local_today = now.astimezone(ZoneInfo(tz_name)).date()
    current = local_today - timedelta(days=local_today.weekday())
    return [current - timedelta(weeks=offset) for offset in range(weeks - 1, -1, -1)]


def _local_monday(instant: datetime, tz: ZoneInfo) -> date:
    local = instant.astimezone(tz).date()
    return local - timedelta(days=local.weekday())


def _current_score(rows: list[dict]) -> dict | None:
    if not rows:
        return None
    return max(rows, key=lambda row: (int(row.get("revision_seq") or 0), str(row.get("created_at") or "")))


def _classify(score_row: dict | None) -> tuple[str, dict | None, str | None]:
    """(bucket, counts, playbook_version_id). bucket is scored / without_playbook / without_score."""
    if score_row is None:
        return "without_score", None, None
    score = score_row.get("score") if isinstance(score_row.get("score"), dict) else {}
    status = score.get("status")
    if status == "unavailable" or score.get("reason") == "missing_playbook":
        return "without_playbook", None, None
    if status not in _SCORED:
        return "without_score", None, None
    counts = {key: int(score.get(key) or 0) for key in _COUNT_KEYS}
    version = score_row.get("playbook_version_id") or score.get("playbook_version_id")
    return "scored", counts, (str(version) if version else None)


def _empty_week(week_start: date) -> dict:
    return {
        "week_start": week_start.isoformat(),
        "interactions": 0,
        "scored": 0,
        "without_playbook": 0,
        "without_score": 0,
        "parts": [],
        "versions": set(),
        "motion_versions": set(),
    }


def _finish_week(raw: dict, *, new_version: bool) -> dict:
    metrics = aggregate_adherence(raw["parts"]) if raw["parts"] else None
    adherence = metrics["adherence"] if metrics else None
    if raw["interactions"] == 0:
        state = "gap"
    elif adherence is None:
        state = "unscored"
    else:
        state = "scored"
    return {
        "week_start": raw["week_start"],
        "state": state,
        "interactions": raw["interactions"],
        "scored": raw["scored"],
        "without_playbook": raw["without_playbook"],
        "without_score": raw["without_score"],
        "met_steps": metrics["met_steps"] if metrics else 0,
        "missed_steps": metrics["missed_steps"] if metrics else 0,
        "applicable_steps": metrics["applicable_steps"] if metrics else 0,
        "unknown_steps": metrics["unknown_steps"] if metrics else 0,
        "not_applicable_steps": metrics["not_applicable_steps"] if metrics else 0,
        "adherence": adherence,
        "coverage": metrics["coverage"] if metrics else None,
        "sample_limited": 1 <= raw["scored"] < _SAMPLE_LIMIT,
        "playbook_version_ids": sorted(raw["versions"]),
        "new_playbook_version": new_version,
    }


def _series(entries: list[dict], starts: list[date]) -> dict:
    """entries: {week, bucket, counts, version, motion}. One output week per start, in order."""
    by_week = {start: _empty_week(start) for start in starts}
    for entry in entries:
        raw = by_week.get(entry["week"])
        if raw is None:
            continue
        raw["interactions"] += 1
        raw[entry["bucket"]] += 1
        if entry["bucket"] == "scored":
            raw["parts"].append(entry["counts"])
            if entry["version"]:
                raw["versions"].add(entry["version"])
                raw["motion_versions"].add((entry["motion"], entry["version"]))
    seen: dict[object, set[str]] = {}
    weeks: list[dict] = []
    for start in starts:
        raw = by_week[start]
        changed = False
        for motion, version in sorted(raw["motion_versions"], key=lambda pair: (str(pair[0]), pair[1])):
            earlier = seen.get(motion)
            if earlier and version not in earlier:
                changed = True
        for motion, version in raw["motion_versions"]:
            seen.setdefault(motion, set()).add(version)
        weeks.append(_finish_week(raw, new_version=changed))
    return {"weeks": weeks}


def build_adherence_trend(
    *,
    memos: list[dict],
    scores: list[dict],
    reps: list[dict],
    starts: list[date],
    tz_name: str = DEFAULT_TZ,
    include_team: bool = True,
) -> dict:
    """Pure aggregation. reps are {userId, name} already in display order."""
    tz = ZoneInfo(tz_name)
    rep_ids = [str(rep["userId"]) for rep in reps]
    allowed = set(rep_ids)
    scores_by_memo: dict[str, list[dict]] = {}
    for row in scores:
        scores_by_memo.setdefault(str(row.get("memo_id")), []).append(row)
    entries_by_rep: dict[str, list[dict]] = {uid: [] for uid in rep_ids}
    for memo in memos:
        uid = str(memo.get("user_id") or "")
        if uid not in allowed:
            continue
        if memo.get("screening_outcome") in _NOT_CONVERSATIONS or memo.get("status") == "failed":
            continue
        instant = _parse_instant(memo.get("capture_started_at")) or _parse_instant(memo.get("created_at"))
        if instant is None:
            continue
        bucket, counts, version = _classify(_current_score(scores_by_memo.get(str(memo.get("id")), [])))
        entries_by_rep[uid].append(
            {
                "week": _local_monday(instant, tz),
                "bucket": bucket,
                "counts": counts,
                "version": version,
                "motion": memo.get("sales_motion_key"),
            }
        )
    rows = [
        {"user_id": str(rep["userId"]), "name": rep.get("name") or "", **_series(entries_by_rep[str(rep["userId"])], starts)}
        for rep in reps
    ]
    team = None
    if include_team:
        team = _series([entry for uid in rep_ids for entry in entries_by_rep[uid]], starts)
    return {"team": team, "reps": rows}


def _window_start_utc(first_monday: date, tz_name: str) -> datetime:
    return datetime.combine(first_monday, time.min, tzinfo=ZoneInfo(tz_name)).astimezone(timezone.utc)


def _read_memos(supabase, company_id: str, member_ids: list[str], *, since: datetime,
                user_id: str | None, motion: str | None) -> list[dict]:
    """capture_started_at <= created_at, so created_at >= window start loses no conversation."""
    rows: list[dict] = []
    offset = 0
    while True:
        query = (
            supabase.table("memos")
            .select("id,user_id,company_id,sales_motion_key,screening_outcome,status,capture_started_at,created_at")
            .in_("user_id", member_ids)
            .or_(f"company_id.eq.{company_id},company_id.is.null")
            .gte("created_at", since.isoformat())
        )
        if user_id:
            query = query.eq("user_id", user_id)
        if motion:
            query = query.eq("sales_motion_key", motion)
        page = list(query.order("id").range(offset, offset + _MEMO_PAGE - 1).execute().data or [])
        rows.extend(page)
        if len(page) < _MEMO_PAGE:
            return rows
        offset += _MEMO_PAGE


def _read_scores(supabase, memo_ids: list[str]) -> list[dict]:
    rows: list[dict] = []
    for index in range(0, len(memo_ids), _SCORE_BATCH):
        batch = memo_ids[index : index + _SCORE_BATCH]
        result = (
            supabase.table("memo_scores")
            .select("memo_id,revision_seq,playbook_version_id,score,created_at")
            .in_("memo_id", batch)
            .execute()
        )
        rows.extend(result.data or [])
    return rows


def adherence_trend(
    supabase,
    company_id: str,
    *,
    role: str,
    weeks: int = DEFAULT_WEEKS,
    now: datetime | None = None,
    user_id: str | None = None,
    motion: str | None = None,
    tz_name: str = DEFAULT_TZ,
) -> dict:
    """Owner/admin only. Callers outside GET /team/adherence/trend must also check FLAG."""
    assert_team_reader(role)
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    count = max(1, min(MAX_WEEKS, int(weeks)))
    starts = week_starts(now=instant, weeks=count, tz_name=tz_name)
    current = starts[-1]
    header = {
        "timezone": tz_name,
        "weeks": [
            {
                "week_start": start.isoformat(),
                "week_end": (start + timedelta(days=6)).isoformat(),
                "in_progress": start == current,
            }
            for start in starts
        ],
    }
    filter_user = (user_id or "").strip() or None
    filter_motion = (motion or "").strip() or None
    reps = load_team_reps(supabase, company_id)
    if not reps:
        # The owner is always a member, so no members means the read failed.
        return {**header, "coverage": "unavailable", "team": None, "reps": []}
    if filter_user:
        reps = [rep for rep in reps if str(rep.get("userId")) == filter_user]
    if not reps:
        return {**header, "coverage": "complete", "team": None, "reps": []}
    member_ids = [str(rep["userId"]) for rep in reps]
    try:
        memos = _read_memos(
            supabase,
            company_id,
            member_ids,
            since=_window_start_utc(starts[0], tz_name),
            user_id=filter_user,
            motion=filter_motion,
        )
        scores = _read_scores(supabase, [str(memo.get("id")) for memo in memos if memo.get("id")])
    except Exception:
        return {**header, "coverage": "unavailable", "team": None, "reps": []}
    body = build_adherence_trend(
        memos=memos,
        scores=scores,
        reps=reps,
        starts=starts,
        tz_name=tz_name,
        include_team=filter_user is None,
    )
    return {**header, "coverage": "complete", **body}
