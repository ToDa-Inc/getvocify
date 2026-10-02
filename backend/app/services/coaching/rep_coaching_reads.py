"""Reads for the rep coaching tab. Any failed read returns empty, never a guess."""

from __future__ import annotations

from datetime import datetime

from app.services.playbooks.live import live_snapshot
from app.services.team_insights.aggregate import load_team_reps

_MEMO_BASE = (
    "id,user_id,company_id,sales_motion_key,screening_outcome,audio_duration,"
    "capture_started_at,created_at,hubspot_contact_id,hubspot_deal_id"
)
# Only the parts of the analysis coaching reads: the whole extraction (evidence, the call read turn
# by turn, CRM fields) is several times heavier and made every coaching screen wait for it.
_EXTRACTION_PARTS = (
    "observations:extraction->intelligence->playbook_observations,"
    "call_type:extraction->intelligence->call->>call_type,"
    "reached_conversation:extraction->intelligence->call->reached_conversation,"
    "outcome:extraction->intelligence->next->outcome,"
    "summary:extraction->>summary"
)
_MEMO_COLUMNS = _MEMO_BASE + "," + _EXTRACTION_PARTS
_MEMO_COLUMNS_FULL = _MEMO_BASE + ",extraction"


def _as_extraction(row: dict) -> dict:
    """The trimmed row back in the shape the coaching engine reads (extraction.intelligence...)."""
    if "extraction" in row or "observations" not in row:
        return row
    out = {k: v for k, v in row.items() if k not in ("observations", "call_type", "reached_conversation", "outcome", "summary")}
    call = {k: row.get(k) for k in ("call_type", "reached_conversation") if row.get(k) is not None}
    intelligence = {"playbook_observations": row.get("observations")}
    if call:
        intelligence["call"] = call
    if row.get("outcome"):
        intelligence["next"] = {"outcome": row["outcome"]}
    out["extraction"] = {"intelligence": intelligence, "summary": row.get("summary")}
    return out
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
    for columns in (_MEMO_COLUMNS + ",rep_outcome", _MEMO_COLUMNS, _MEMO_COLUMNS_FULL + ",rep_outcome", _MEMO_COLUMNS_FULL):
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
            rows = [_as_extraction(row) for row in rows]
            rows.sort(key=lambda row: (str(row.get("created_at") or ""), str(row.get("id") or "")))
            # A meeting the rep marked in the CRM (the deal moved to the meeting-booked stage) is
            # their declaration too: it settles the meeting step like rep_outcome does.
            from app.services.coaching.crm_meetings import apply_rep_meetings

            return apply_rep_meetings(supabase, rows, batch=_IN_BATCH)
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
    """{published, steps, entries} of the flow's live published version (none when it is paused, deleted or
    was never published)."""
    empty = {"published": False, "steps": [], "entries": []}
    try:
        snapshot = live_snapshot(supabase, company_id, motion)
    except Exception:
        return empty
    if not snapshot:
        return empty
    steps = [s for s in snapshot["steps"] if isinstance(s, dict) and s.get("step_id")]
    entries = [e for e in snapshot["entries"] if isinstance(e, dict)]
    return {"published": bool(steps), "steps": steps, "entries": entries}
