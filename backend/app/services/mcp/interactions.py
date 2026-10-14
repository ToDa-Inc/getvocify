"""The interaction record an agent reads: one call, meeting, visit or voice note, already prepared.

A list row carries the structured facts (outcome, objection categories, competitors, score), so an agent
can count and group a week without opening every interaction. The full record adds what the dashboard's
memo page shows: summary, commitments, objections with the playbook's approved answer, coaching, quotes.
Everything here reads what the screens read (stored extraction, score and debrief); nothing is
re-derived. Sync on purpose: the server runs it in a worker thread.
"""

from __future__ import annotations

import base64
import binascii
import json
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Optional

from fastapi import HTTPException

from app.config import settings
from app.services.crm_copilot import brain_tools
from app.services.crm_copilot.actor import AskActor, ScopeError, visible_user_ids
from app.services.crm_copilot.intel_tools import (
    MEMO_COLUMNS,
    _episodes,
    _extraction,
    _first_line,
    _intel,
    _memo_at,
    _rep_names,
)
from app.services.playbooks.catalog import INTERNAL_KEY

USABLE = ("pending_review", "approved")
KINDS = ("call", "meeting", "visit", "voice_note")
OUTCOMES = ("meeting_booked", "follow_up", "not_interested", "disqualified")
DEFAULT_LIMIT = 20
MAX_LIMIT = 50
TRANSCRIPT_PAGE_CHARS = 12_000
_BATCHES = 5
_LIST_COLUMNS = MEMO_COLUMNS + ",rep_outcome,audio_duration"


class NotFound(Exception):
    """No interaction with that id that this caller can read."""


class BadInput(Exception):
    """An argument the agent can fix. The message says how."""


def dashboard_url(memo_id: str) -> str:
    return f"{settings.FRONTEND_URL.rstrip('/')}/dashboard/memos/{memo_id}"


def _ctx(supabase: Any) -> SimpleNamespace:
    return SimpleNamespace(supabase=supabase, cards=[])


def _company_service(supabase: Any):
    from app.services.company import CompanyService

    return CompanyService(supabase)


def _compact(row: dict) -> dict:
    """Empty fields cost the agent tokens and say nothing."""
    return {k: v for k, v in row.items() if v not in (None, "", [], {})}


def _date(value: Optional[str], name: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError as error:
        raise BadInput(f"{name} must be an ISO date like 2026-10-01 or 2026-10-01T09:00:00Z") from error
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _encode_cursor(created_at: str) -> str:
    return base64.urlsafe_b64encode(json.dumps({"before": created_at}).encode()).decode()


def _decode_cursor(cursor: Optional[str]) -> Optional[str]:
    if not cursor:
        return None
    try:
        before = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode()).get("before")
    except (binascii.Error, ValueError, AttributeError) as error:
        raise BadInput("cursor is not one this server returned; repeat the call without it") from error
    if not isinstance(before, str) or not before:
        raise BadInput("cursor is not one this server returned; repeat the call without it")
    return before


def _competitors(memo: dict) -> list[str]:
    names = list(_extraction(memo).get("competitors") or [])
    names += [c.get("name") for c in _intel(memo).get("competitor_mentions") or [] if isinstance(c, dict)]
    seen: dict[str, str] = {}
    for raw in names:
        text = str(raw or "").strip()
        if text:
            seen.setdefault(text.casefold(), text)
    return sorted(seen.values(), key=str.casefold)


def _scores(supabase: Any, memo_ids: list[str]) -> dict[str, Any]:
    """{memo_id: score value} from the current stored score row. A failed read is no score, not an error."""
    from app.services.coaching.score_rows import current_scores

    if not memo_ids:
        return {}
    try:
        rows = (
            supabase.table("memo_scores")
            .select("memo_id,score,revision_seq,created_at,input_revision")
            .in_("memo_id", memo_ids)
            .execute()
            .data
            or []
        )
    except Exception:  # noqa: BLE001
        return {}
    out = {}
    for memo_id, row in current_scores(rows).items():
        score = row.get("score") if isinstance(row.get("score"), dict) else {}
        if score.get("value") is not None:
            out[memo_id] = score["value"]
    return out


def _row(memo: dict, rep: Optional[str], score: Any) -> dict:
    extraction = _extraction(memo)
    episodes = _episodes(memo)
    duration = memo.get("audio_duration")
    return _compact(
        {
            "id": str(memo.get("id")),
            "at": _memo_at(memo).isoformat(),
            "kind": memo.get("interaction_kind") or "call",
            "contact": str(extraction.get("contactName") or "").strip() or None,
            "company": str(extraction.get("companyName") or "").strip() or None,
            "contact_id": memo.get("hubspot_contact_id"),
            "deal_id": memo.get("hubspot_deal_id"),
            "rep": rep,
            "duration_seconds": int(duration) if isinstance(duration, (int, float)) else None,
            "outcome": memo.get("rep_outcome"),
            "summary": _first_line(extraction.get("summary")),
            "interest": _intel(memo).get("interest"),
            "objections": sorted({e["category"] for e in episodes if e["kind"] == "objection"}),
            "obstacles": sorted({e["category"] for e in episodes if e["kind"] == "obstacle"}),
            "competitors": _competitors(memo),
            "next_steps": [str(s)[:160] for s in (extraction.get("nextSteps") or [])[:2]],
            "score": score,
            "url": dashboard_url(str(memo.get("id"))),
        }
    )


def _matches(memo: dict, *, kind: Optional[str], category: Optional[str], text: Optional[str]) -> bool:
    if memo.get("status") not in USABLE or not _extraction(memo) or memo.get("sales_motion_key") == INTERNAL_KEY:
        return False
    if kind and (memo.get("interaction_kind") or "call") != kind:
        return False
    if category and not any(e["category"] == category for e in _episodes(memo)):
        return False
    if text:
        extraction = _extraction(memo)
        haystack = " ".join(
            str(extraction.get(k) or "") for k in ("contactName", "companyName", "summary")
        ).casefold()
        if text not in haystack:
            return False
    return True


def list_interactions(
    supabase: Any,
    actor: AskActor,
    *,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    rep_id: Optional[str] = None,
    contact_id: Optional[str] = None,
    deal_id: Optional[str] = None,
    kind: Optional[str] = None,
    outcome: Optional[str] = None,
    objection_category: Optional[str] = None,
    q: Optional[str] = None,
    cursor: Optional[str] = None,
    limit: Optional[int] = None,
) -> dict:
    """Newest first. Raises ScopeError for a rep_id outside the caller's view, BadInput for a bad argument."""
    if kind and kind not in KINDS:
        raise BadInput(f"kind must be one of {', '.join(KINDS)}")
    if outcome and outcome not in OUTCOMES:
        raise BadInput(f"outcome must be one of {', '.join(OUTCOMES)}")
    size = DEFAULT_LIMIT if limit is None else limit
    if not 1 <= int(size) <= MAX_LIMIT:
        raise BadInput(f"limit must be between 1 and {MAX_LIMIT}")
    size = int(size)
    start, end = _date(date_from, "from"), _date(date_to, "to")
    if end and len(str(date_to).strip()) == 10:  # a bare date means through the end of that day
        end = end + timedelta(days=1)
    before = _decode_cursor(cursor)
    user_ids = visible_user_ids(actor, _company_service(supabase), rep_id)
    category = (objection_category or "").strip().lower() or None
    text = (q or "").strip().casefold() or None
    reps = _rep_names(_ctx(supabase), actor)

    found: list[dict] = []
    exhausted = False
    last_scanned: Optional[str] = None
    batch = max(size * 3, 60)
    for _ in range(_BATCHES):
        query = (
            supabase.table("memos")
            .select(_LIST_COLUMNS)
            .in_("user_id", user_ids)
            .or_(f"company_id.eq.{actor.company_id},company_id.is.null")
            .in_("status", list(USABLE))
        )
        if start:
            query = query.gte("created_at", start.isoformat())
        if end:
            query = query.lt("created_at", end.isoformat())
        if before or last_scanned:
            query = query.lt("created_at", last_scanned or before)
        if contact_id:
            query = query.eq("hubspot_contact_id", str(contact_id))
        if deal_id:
            query = query.eq("hubspot_deal_id", str(deal_id))
        if outcome:
            query = query.eq("rep_outcome", outcome)
        rows = query.order("created_at", desc=True).limit(batch).execute().data or []
        for memo in rows:
            if _matches(memo, kind=kind, category=category, text=text):
                found.append(memo)
        if rows:
            last_scanned = str(rows[-1].get("created_at"))
        if len(rows) < batch:
            exhausted = True
            break
        if len(found) > size:
            break

    page = found[:size]
    if len(found) > size:
        next_cursor = _encode_cursor(str(page[-1].get("created_at")))
    elif not exhausted and last_scanned:
        next_cursor = _encode_cursor(last_scanned)
    else:
        next_cursor = None
    scores = _scores(supabase, [str(m.get("id")) for m in page])
    items = [_row(m, reps.get(str(m.get("user_id"))), scores.get(str(m.get("id")))) for m in page]
    return {"interactions": items, "count": len(items), "next_cursor": next_cursor}


def _transcript_page(text: str, cursor: Optional[str]) -> dict:
    try:
        offset = int(cursor or 0)
    except ValueError as error:
        raise BadInput("transcript_cursor must be the value a previous call returned") from error
    if offset < 0 or offset > len(text):
        raise BadInput("transcript_cursor is out of range; repeat without it to start from the beginning")
    end = min(len(text), offset + TRANSCRIPT_PAGE_CHARS)
    if end < len(text):
        newline = text.rfind("\n", offset + TRANSCRIPT_PAGE_CHARS // 2, end)
        if newline > offset:
            end = newline + 1
    return _compact(
        {
            "text": text[offset:end],
            "chars": len(text),
            "next_cursor": str(end) if end < len(text) else None,
        }
    )


def _coaching(score: dict, brief: dict) -> dict:
    if not score or score.get("status") == "unavailable":
        reason = (score or {}).get("reason") or "not_scored"
        return {"status": "not_scored", "reason": reason}
    coach = brief.get("coach") if isinstance(brief.get("coach"), dict) else {}
    kept, fix = coach.get("kept") or None, coach.get("fix") or None
    return _compact(
        {
            "score": score.get("value"),
            "adherence": score.get("adherence"),
            "coverage": score.get("coverage"),
            "strengths": score.get("strengths"),
            "improvements": score.get("improvements"),
            "kept": _compact({"step": kept.get("label"), "quote": kept.get("quote")}) if kept else None,
            "fix": _compact({"step": fix.get("label"), "criterion": fix.get("criterion"), "say": fix.get("say")}) if fix else None,
            "missed": [m.get("label") for m in brief.get("missed") or [] if isinstance(m, dict) and m.get("label")],
        }
    )


def get_interaction(
    supabase: Any,
    membership,
    actor: AskActor,
    interaction_id: str,
    *,
    include_transcript: bool = False,
    transcript_cursor: Optional[str] = None,
    transcripts_allowed: bool = False,
) -> dict:
    """The full record. Raises NotFound unless the caller can read it (same rule as GET /memos/{id})."""
    from app.api import coaching as coaching_api
    from app.api.memos import _require_viewable_memo

    try:
        memo_id = str(uuid.UUID(str(interaction_id).strip()))
    except ValueError as error:
        raise NotFound(interaction_id) from error
    try:
        memo, authors = _require_viewable_memo(supabase, memo_id, actor.user_id)
    except HTTPException as error:
        raise NotFound(memo_id) from error

    status = memo.get("status")
    if status not in USABLE or not _extraction(memo):
        state = "failed" if status == "failed" else "processing"
        note = "Processing failed for this interaction." if state == "failed" else "Still being processed; try again in a few minutes."
        return {"id": memo_id, "status": state, "note": note, "url": dashboard_url(memo_id)}

    extraction, intel = _extraction(memo), _intel(memo)
    owner = authors.get(str(memo.get("user_id") or "")) or {}
    episodes = _episodes(memo)
    open_categories = {e["category"] for e in episodes if e["kind"] == "objection" and e["state"] in ("open", "unknown")}
    answers: dict = {}
    if open_categories:
        published, _ = brain_tools.published_answers(_ctx(supabase), actor)
        answers = {c: published[c]["answer"] for c in open_categories if c in published}
    objections = [
        _compact(
            {
                "kind": e["kind"],
                "category": e["category"],
                "state": e["state"],
                "quote": e["quote"],
                "rep_response": e["response"],
                "approved_answer": answers.get(e["category"]) if e["kind"] == "objection" else None,
            }
        )
        for e in episodes
    ]
    meeting = intel.get("meeting") if isinstance(intel.get("meeting"), dict) else {}
    evidence = [
        _compact(
            {
                "id": item.get("id"),
                "quote": item.get("quote"),
                "speaker": item.get("speaker_role"),
                "at_ms": item.get("start_ms"),
            }
        )
        for item in (intel.get("evidence") or [])[:12]
        if isinstance(item, dict) and item.get("quote")
    ]

    score: dict = {}
    brief: dict = {}
    if memo.get("sales_motion_key") != INTERNAL_KEY:
        try:
            score = coaching_api.get_memo_score(memo_id, membership=membership, supabase=supabase) or {}
            brief = coaching_api.get_memo_brief(memo_id, membership=membership, supabase=supabase) or {}
        except HTTPException:
            score, brief = {}, {}

    record = _compact(
        {
            "id": memo_id,
            "status": status,
            "at": _memo_at(memo).isoformat(),
            "kind": memo.get("interaction_kind") or "call",
            "rep": owner.get("name"),
            "duration_seconds": int(memo["audio_duration"]) if isinstance(memo.get("audio_duration"), (int, float)) else None,
            "contact": _compact(
                {
                    "name": extraction.get("contactName"),
                    "role": extraction.get("contactRole"),
                    "email": extraction.get("contactEmail"),
                    "phone": extraction.get("contactPhone"),
                    "company": extraction.get("companyName"),
                }
            ),
            "deal": _compact(
                {
                    "stage": extraction.get("dealStage"),
                    "amount": extraction.get("dealAmount"),
                    "currency": extraction.get("dealCurrency") if extraction.get("dealAmount") is not None else None,
                    "close_date": extraction.get("closeDate"),
                }
            ),
            "crm": _compact(
                {
                    "contact_id": memo.get("hubspot_contact_id"),
                    "deal_id": memo.get("hubspot_deal_id"),
                    "engagement_id": memo.get("hubspot_engagement_id"),
                }
            ),
            "outcome": memo.get("rep_outcome"),
            "summary": extraction.get("summary"),
            "interest": intel.get("interest"),
            "pains": extraction.get("painPoints"),
            "decision_makers": extraction.get("decisionMakers"),
            "next_steps": extraction.get("nextSteps"),
            "commitments": [
                _compact({"text": c.get("text"), "due_at": c.get("due_at"), "by": c.get("origin")})
                for c in intel.get("commitments") or []
                if isinstance(c, dict) and c.get("text")
            ],
            "meeting": _compact(
                {"agreed": meeting.get("agreed"), "starts_at": meeting.get("starts_at"), "timezone": meeting.get("timezone")}
            ),
            "objections": objections,
            "competitors": _competitors(memo),
            "coaching": _coaching(score, brief),
            "rep_notes": memo.get("user_notes"),
            "attendees": [
                _compact({"name": a.get("name"), "email": a.get("email")})
                for a in memo.get("attendees") or []
                if isinstance(a, dict)
            ],
            "evidence": evidence,
            "url": dashboard_url(memo_id),
        }
    )
    if include_transcript:
        transcript = str(memo.get("transcript") or "")
        if not transcripts_allowed:
            record["transcript"] = {"available": False, "note": "Your workspace admin has turned off transcripts for AI agents."}
        elif not transcript.strip():
            record["transcript"] = {"available": False, "note": "This interaction has no transcript."}
        else:
            record["transcript"] = _transcript_page(transcript, transcript_cursor)
    return record


__all__ = ["BadInput", "NotFound", "ScopeError", "get_interaction", "list_interactions"]
