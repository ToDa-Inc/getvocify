"""Reads for the rep coaching tab. Any failed read returns empty, never a guess."""

from __future__ import annotations

from datetime import datetime

from app.services.team_insights.aggregate import load_team_reps

_MEMO_COLUMNS = (
    "id,user_id,company_id,sales_motion_key,screening_outcome,audio_duration,"
    "extraction,capture_started_at,created_at"
)
_PATTERN_COLUMNS = "memo_id,category,kind,resolution,response,superseded,created_at"
_PAGE_SIZE = 1000
_IN_BATCH = 100


def _memo_query(supabase, columns: str, company_id: str, user_ids: list[str], start: datetime):
    # Older memos have no company_id; a member's memo without one still belongs to the company.
    return (
        supabase.table("memos")
        .select(columns)
        .in_("user_id", user_ids)
        .or_(f"company_id.eq.{company_id},company_id.is.null")
        .gte("created_at", start.isoformat())
    )


def _batches(values: list[str]):
    """`.in_()` lists stay short enough not to overflow the request URL."""
    for index in range(0, len(values), _IN_BATCH):
        yield values[index : index + _IN_BATCH]


def load_memos(
    supabase, company_id: str, user_ids: list[str], *, start: datetime, motion: str | None = None
) -> list[dict]:
    """Memos of these users created since `start`, oldest first (created_at, then id).
    rep_outcome is selected when the column exists."""
    if not user_ids:
        return []
    for columns in (_MEMO_COLUMNS + ",rep_outcome", _MEMO_COLUMNS):
        try:
            rows: list[dict] = []
            for batch in _batches(list(user_ids)):
                offset = 0
                # PostgREST caps a response (1000 rows by default): page so a busy SDR team's
                # weeks are not silently truncated.
                while True:
                    query = _memo_query(supabase, columns, company_id, batch, start)
                    if motion:
                        query = query.eq("sales_motion_key", motion)
                    page = list(
                        query.order("created_at").order("id").range(offset, offset + _PAGE_SIZE - 1).execute().data
                        or []
                    )
                    rows.extend(page)
                    if len(page) < _PAGE_SIZE:
                        break
                    offset += _PAGE_SIZE
            rows.sort(key=lambda row: (str(row.get("created_at") or ""), str(row.get("id") or "")))
            return rows
        except Exception:
            continue
    return []


def load_peer_ids(supabase, company_id: str, user_id: str) -> list[str]:
    """Active company members other than the caller."""
    return [rep["userId"] for rep in load_team_reps(supabase, company_id) if rep["userId"] != user_id]


def load_patterns(supabase, memo_ids: list[str]) -> list[dict]:
    if not memo_ids:
        return []
    try:
        rows: list[dict] = []
        for batch in _batches(list(memo_ids)):
            offset = 0
            while True:
                page = list(
                    supabase.table("interaction_patterns")
                    .select(_PATTERN_COLUMNS)
                    .in_("memo_id", batch)
                    .order("memo_id")
                    .order("pattern_id")
                    .order("input_revision")
                    .range(offset, offset + _PAGE_SIZE - 1)
                    .execute()
                    .data
                    or []
                )
                rows.extend(page)
                if len(page) < _PAGE_SIZE:
                    break
                offset += _PAGE_SIZE
        return rows
    except Exception:
        return []


def load_published_playbook(supabase, company_id: str, motion: str) -> dict:
    """{published, steps, entries} of the flow's active published version."""
    empty = {"published": False, "steps": [], "entries": []}
    try:
        playbooks = (
            supabase.table("playbooks")
            .select("id,active_version_id")
            .eq("company_id", company_id)
            .eq("sales_motion_key", motion)
            .limit(1)
            .execute()
        ).data or []
        active = playbooks[0].get("active_version_id") if playbooks else None
        if not active:
            return empty
        versions = (
            supabase.table("playbook_versions")
            .select("id,status,steps,entries")
            .eq("id", active)
            .eq("status", "published")
            .limit(1)
            .execute()
        ).data or []
    except Exception:
        return empty
    if not versions:
        return empty
    steps = [s for s in versions[0].get("steps") or [] if isinstance(s, dict) and s.get("step_id")]
    entries = [e for e in versions[0].get("entries") or [] if isinstance(e, dict)]
    return {"published": bool(steps), "steps": steps, "entries": entries}
