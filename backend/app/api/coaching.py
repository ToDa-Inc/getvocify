"""GET a stored score. This route does not recompute it."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from fastapi.responses import JSONResponse

from app.deps import get_membership, get_supabase
from app.services.coaching.best import FLAG as PLAYBOOK_TAB_FLAG, best_by_flow
from app.services.coaching.brief_preferences import highlight_at, read_preference
from app.services.coaching.briefs import absent_brief
from app.services.coaching import better_reply as better
from app.services.coaching import rep_coaching as engine
from app.services.coaching import rep_coaching_reads as reads
from app.services.coaching.rep_focus import FLOW_WEEKS, motion_for_flow, published_flows, resolve_flow
from app.services.coaching.score_rows import current_score, current_scores
from app.services.activity_scope import effective_visibility, memo_readable_by
from app.services.company import CompanyService, Membership
from app.services.feature_flags import is_enabled
from app.services.playbooks.catalog import INTERNAL_KEY
from app.services.playbooks.step_identity import StepMatcher
from app.services.team_insights.aggregate import load_team_reps, madrid_week_bounds

router = APIRouter(prefix="/api/v1", tags=["coaching"])


def _parse_instant(raw: object) -> datetime:
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    text = str(raw).replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _brief_ready_at(row: dict, body: dict) -> datetime:
    if body.get("ready_at"):
        return _parse_instant(body["ready_at"])
    if row.get("created_at"):
        return _parse_instant(row["created_at"])
    return datetime.now(timezone.utc)


def _attach_highlight(body: dict, *, user_id: str, ready_at: datetime) -> dict:
    preference = read_preference(user_id)
    shown = highlight_at(ready_at, preference)
    iso = shown.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        **body,
        "highlight": {
            "highlight_mode": preference["highlight_mode"],
            "highlight_at": iso,
            "timezone": preference["timezone"],
        },
    }


def _require_readable_memo(supabase, membership: Membership, memo_id: str) -> dict:
    """404 unless the memo is in the caller's company AND readable by the caller: their own,
    a manager's / visibility=team reader's view of the company, or (T4/D8) an AE reading the
    SDR's memo of a handed-off contact. Same rule as GET /memos/{id}."""
    result = (
        supabase.table("memos")
        .select("id,company_id,user_id,hubspot_contact_id,sales_motion_key")
        .eq("id", memo_id)
        .execute()
    )
    rows = result.data or []
    memo = rows[0] if rows else None
    if not memo or memo.get("company_id") != membership.company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memo no encontrado")
    viewer_id = membership.user_id
    visibility = effective_visibility(supabase, membership)

    def readable(handoff_sdr_ids: set | None = None) -> bool:
        return memo_readable_by(
            viewer_id=viewer_id,
            owner_user_id=str(memo.get("user_id") or ""),
            viewer_role=membership.role,
            same_company=True,
            viewer_visibility=visibility,
            handoff_sdr_ids=handoff_sdr_ids,
        )

    if readable():
        return memo
    contact_id = str(memo.get("hubspot_contact_id") or "") or None
    if contact_id:
        from app.api.memos import _active_handoff_sdr_ids_for_contact

        try:
            members = CompanyService(supabase).list_members(membership.company_id)
        except Exception:
            members = []
        if readable(_active_handoff_sdr_ids_for_contact(
            supabase, membership=membership, members=members, contact_id=contact_id, viewer_id=viewer_id,
        )):
            return memo
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memo no encontrado")


@router.get("/memos/{memo_id}/score")
def get_memo_score(
    memo_id: str,
    membership: Membership = Depends(get_membership),
    supabase=Depends(get_supabase),
):
    memo = _require_readable_memo(supabase, membership, memo_id)
    # An `internal` memo is never scored: a score stored before it was retagged is not shown
    # (the row stays, so retagging it back to a real type shows it again).
    internal = memo.get("sales_motion_key") == INTERNAL_KEY
    scores = []
    if not internal:
        stored = (
            supabase.table("memo_scores")
            .select("*")
            .eq("memo_id", memo_id)
            .execute()
        )
        scores = stored.data or []
    if not scores:
        return {
            "status": "unavailable",
            "value": None,
            # "internal" is never scored; "not_scored" may still get a score.
            "reason": "internal" if internal else "not_scored",
            "strengths": [],
            "improvements": [],
            "crm_outcome": None,
            "adherence": None,
            "coverage": None,
        }
    # Same revision_seq (a re-read of the same conversation, e.g. a company moving to a newer C04
    # prompt): the most recently written score wins. `blocks` (PLAYBOOK_QUALIFICATION_ENABLED)
    # travels inside the stored score, so it reaches the client as is.
    current = current_score(scores)
    body = dict(current.get("score") or {})
    body["playbook_version_id"] = current.get("playbook_version_id")
    return body


@router.get("/memos/{memo_id}/brief")
def get_memo_brief(
    memo_id: str,
    membership: Membership = Depends(get_membership),
    supabase=Depends(get_supabase),
):
    _require_readable_memo(supabase, membership, memo_id)
    stored = (
        supabase.table("post_interaction_briefs")
        .select("*")
        .eq("memo_id", memo_id)
        .execute()
    )
    briefs = stored.data or []
    if not briefs:
        return absent_brief()
    current = max(briefs, key=lambda row: row.get("revision_seq") or 0)
    body = dict(current.get("body") or {})
    body["status"] = current.get("status")
    body["input_revision"] = current.get("input_revision")
    ready_at = _brief_ready_at(current, body)
    return _attach_highlight(body, user_id=membership.user_id, ready_at=ready_at)


def _best_week_bounds(week: Optional[str]) -> tuple[datetime, datetime]:
    if not week:
        return madrid_week_bounds()
    try:
        parsed = _parse_instant(week)
    except ValueError:
        return madrid_week_bounds()
    return madrid_week_bounds(now=parsed)


def _load_best_rows(supabase, company_id: str, *, start: datetime, end: datetime) -> list[dict]:
    """Scored memos created in [start, end), for `best_by_flow` to rank and filter.

    `created_at` (not `capture_started_at`) bounds the DB query, matching the rest of the
    codebase's date filters; `best_by_flow` still checks its own instant per row, so a
    memo whose only date is `capture_started_at` is not silently dropped."""
    reps = load_team_reps(supabase, company_id)
    names = {rep["userId"]: rep["name"] for rep in reps}
    member_ids = list(names.keys())
    start_iso = start.isoformat()
    end_iso = end.isoformat()
    try:
        query = (
            supabase.table("memos")
            .select("id,user_id,company_id,sales_motion_key,extraction,capture_started_at,created_at")
            .gte("created_at", start_iso)
            .lt("created_at", end_iso)
        )
        if member_ids:
            query = query.in_("user_id", member_ids).or_(
                f"company_id.eq.{company_id},company_id.is.null"
            )
        else:
            query = query.eq("company_id", company_id)
        memo_rows = list(query.execute().data or [])
    except Exception:
        return []
    memo_ids = [str(memo.get("id")) for memo in memo_rows if memo.get("id")]
    scores_by_memo: dict[str, dict] = {}
    if memo_ids:
        try:
            scored = (
                supabase.table("memo_scores")
                .select("memo_id,score,revision_seq,created_at,input_revision")
                .in_("memo_id", memo_ids)
                .execute()
            )
            for memo_id, item in current_scores(scored.data or []).items():
                scores_by_memo[memo_id] = {"score": item.get("score") or {}, "revision_seq": item.get("revision_seq") or 0}
        except Exception:
            scores_by_memo = {}
    rows: list[dict] = []
    for memo in memo_rows:
        memo_id = str(memo.get("id"))
        stored = scores_by_memo.get(memo_id)
        if not stored:
            continue
        score = stored["score"] if isinstance(stored["score"], dict) else {}
        extraction = memo.get("extraction") if isinstance(memo.get("extraction"), dict) else {}
        intelligence = extraction.get("intelligence") if isinstance(extraction.get("intelligence"), dict) else {}
        user_id = str(memo.get("user_id") or "")
        rows.append({
            "memo_id": memo_id,
            "user_id": user_id,
            "author": names.get(user_id, ""),
            "sales_motion_key": memo.get("sales_motion_key"),
            "observed_at": memo.get("capture_started_at") or memo.get("created_at"),
            "value": score.get("value"),
            "evidence": intelligence.get("evidence") or [],
        })
    return rows


@router.get("/coaching/best")
async def get_coaching_best(
    week: Optional[str] = Query(None),
    membership: Membership = Depends(get_membership),
    supabase=Depends(get_supabase),
):
    """T11: the week's top 3 interactions per flow. Every company member can read this;
    whether they can open a listed memo is still decided by the memo's own visibility."""
    if not is_enabled(supabase, membership.company_id, PLAYBOOK_TAB_FLAG):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    start, end = _best_week_bounds(week)
    rows = _load_best_rows(supabase, membership.company_id, start=start, end=end)
    body = best_by_flow(rows, start=start, end=end)
    return JSONResponse(body)


# --- Rep coaching tab: always the caller's own data --------------------------------------

_OWN_WEEKS = FLOW_WEEKS  # also the window that decides a general rep's flow
_PEER_WEEKS = 4
STEP_WINDOW_WEEKS = 4
_MAX_MOMENTS = 3
_MIN_PEERS = 3  # an anonymous example needs this many distinct contributors

Flow = Literal["sdr", "ae"]


def _week_starts(count: int) -> list[datetime]:
    """Monday 00:00 Madrid (UTC) of the last `count` weeks, oldest first, current week last."""
    starts = [madrid_week_bounds()[0]]
    while len(starts) < count:
        starts.insert(0, madrid_week_bounds(now=starts[0] - timedelta(hours=12))[0])
    return starts


def _rows_of(memos: list[dict]) -> list[dict]:
    return [row for row in (engine.interaction_row(memo) for memo in memos) if row is not None]


def _in_window(rows: list[dict], start: datetime, end: datetime) -> list[dict]:
    return [r for r in rows if start <= engine.parse_instant(r["observed_at"]) < end]


def _rep_context(
    supabase, membership: Membership, *, weeks: int = _OWN_WEEKS, peers: bool = True, flow: Optional[str] = None
) -> dict:
    starts = _week_starts(weeks)
    week_start, week_end = madrid_week_bounds()
    # The flow is always resolved over the FLOW_WEEKS window, whatever `weeks` shows.
    flow_start = _week_starts(FLOW_WEEKS)[0]
    peer_start = starts[-1] - timedelta(weeks=_PEER_WEEKS - 1)
    # The rep's calls, their teammates and the teammates' calls do not depend on each other: read
    # them at once instead of one round trip after another.
    with ThreadPoolExecutor(max_workers=3) as pool:
        own_future = pool.submit(
            reads.load_memos, supabase, membership.company_id, [membership.user_id], start=min(starts[0], flow_start)
        )
        peer_ids = reads.load_peer_ids(supabase, membership.company_id, membership.user_id) if peers else []
        peer_future = (
            pool.submit(reads.load_memos, supabase, membership.company_id, peer_ids, start=peer_start)
            if peer_ids else None
        )
        all_own = _rows_of(own_future.result())
        peer_memos = peer_future.result() if peer_future else []
    playbooks: dict[str, dict] = {}

    def playbook_for(motion: str) -> dict:
        if motion not in playbooks:
            playbooks[motion] = reads.load_published_playbook(supabase, membership.company_id, motion)
        return playbooks[motion]

    available = published_flows(playbook_for)
    # `flow` is only honoured for general/NULL reps; SDR/AE always get their own.
    flow_rows = _in_window(all_own, flow_start, week_end)
    flow = resolve_flow(membership.sales_role, flow_rows, available, flow)
    motion = motion_for_flow(flow, flow_rows, playbook_for)
    playbook = playbook_for(motion)
    own = (
        [r for r in _in_window(all_own, starts[0], week_end) if r["motion"] == motion]
        if playbook["published"]
        else []
    )
    peer_rows_by_user: dict[str, list[dict]] = {}
    if peers and playbook["published"]:
        for row in _rows_of([memo for memo in peer_memos if memo.get("sales_motion_key") == motion]):
            peer_rows_by_user.setdefault(row["user_id"], []).append(row)
    return {
        "flow": flow,
        "available_flows": available,
        "motion": motion,
        "week_start": week_start,
        "week_end": week_end,
        "prev_start": madrid_week_bounds(now=week_start - timedelta(hours=12))[0],
        "week_starts": starts,
        "playbook": playbook,
        "own": own,
        "peers": peer_rows_by_user,
        "peer_medians": engine.peer_step_medians(peer_rows_by_user, playbook["steps"]) or {},
    }


def _numbers(rows: list[dict]) -> dict:
    return {
        "conversations": sum(1 for r in rows if r["is_conversation"]),
        "meetings_agreed": sum(1 for r in rows if r["meeting_agreed"]),
        "process_complete": sum(1 for r in rows if engine.process_complete(r)),
        "interactions": len(rows),
    }


def _example_for(step: dict, peer_rows: list[dict]) -> Optional[str]:
    if step.get("example"):
        return str(step["example"])
    moments = _moments(peer_rows, step)
    return moments[0]["quote"] if moments else None


def _moments(peer_rows: list[dict], step: dict) -> list[dict]:
    """Anonymous quotes of a step done in a conversation that ended with a meeting. Empty
    unless at least _MIN_PEERS distinct peers contributed one: with fewer, a quote is
    attributable."""
    step_id, matcher = str(step["step_id"]), StepMatcher([step])
    seen: set[str] = set()
    contributors: set[str] = set()
    out: list[dict] = []
    for row in sorted(peer_rows, key=lambda r: r["observed_at"], reverse=True):
        if not (row["is_conversation"] and row["meeting_agreed"]):
            continue
        for observed in row["steps"]:
            quote = observed["quote"]
            if (
                matcher.match(observed["step_id"], observed.get("criterion")) == step_id
                and observed["state"] == "done"
                and quote
            ):
                contributors.add(row["user_id"])
                if quote not in seen:
                    seen.add(quote)
                    out.append({"quote": quote})
    if len(contributors) < _MIN_PEERS:
        return []
    return out[:_MAX_MOMENTS]


@router.get("/coaching/me/summary")
async def get_my_coaching_summary(
    flow: Optional[Flow] = Query(None),
    membership: Membership = Depends(get_membership),
    supabase=Depends(get_supabase),
):
    ctx = _rep_context(supabase, membership, flow=flow)
    steps = ctx["playbook"]["steps"]
    this_week = _in_window(ctx["own"], ctx["week_start"], ctx["week_end"])
    prev_week = _in_window(ctx["own"], ctx["prev_start"], ctx["week_start"])
    body = {
        "flow": ctx["flow"],
        "available_flows": ctx["available_flows"],
        "motion": ctx["motion"],
        "week_start": engine.madrid_day(ctx["week_start"]).isoformat(),
        "steps": [],
        "numbers": _numbers(this_week),
        "prev_numbers": _numbers(prev_week),
        "focus": None,
        "conversion": None,
        "playbook_published": ctx["playbook"]["published"],
    }
    if not ctx["playbook"]["published"]:
        return body
    medians = ctx["peer_medians"]
    # "Tu semana": a week with no calls yet shows the rep's latest week with calls, not zeros.
    shown_start, shown_rows, shown_prev = ctx["week_start"], this_week, prev_week
    if not this_week:
        starts = ctx["week_starts"]
        for index in range(len(starts) - 2, -1, -1):
            rows = _in_window(ctx["own"], starts[index], starts[index + 1])
            if rows:
                shown_start, shown_rows = starts[index], rows
                shown_prev = _in_window(ctx["own"], starts[index - 1], starts[index]) if index else []
                break
    body["numbers_week_start"] = engine.madrid_day(shown_start).isoformat()
    body["numbers"], body["prev_numbers"] = _numbers(shown_rows), _numbers(shown_prev)
    # "Tus pasos": one week holds a handful of calls where a step applies (follow-ups and calls cut
    # at the door owe only the opening), so a rate over it is noise. The last STEP_WINDOW_WEEKS
    # weeks, against the same span before.
    starts = ctx["week_starts"]
    window_start = starts[-STEP_WINDOW_WEEKS] if len(starts) >= STEP_WINDOW_WEEKS else starts[0]
    window_rows = _in_window(ctx["own"], window_start, ctx["week_end"])
    before_start = starts[-2 * STEP_WINDOW_WEEKS] if len(starts) >= 2 * STEP_WINDOW_WEEKS else starts[0]
    window_prev = _in_window(ctx["own"], before_start, window_start)
    body["steps_window"] = {
        "weeks": STEP_WINDOW_WEEKS,
        "conversations": sum(1 for r in window_rows if r.get("is_conversation", True)),
    }
    prev_rates = {r["step_id"]: r["rate"] for r in engine.step_rates(window_prev, steps)}
    body["steps"] = [
        {
            "step_id": r["step_id"],
            "label": r["label"],
            "rate": r["rate"],
            # The counts behind the rate: "0 %" of one call is not "0 %" of twenty.
            "done": r["done"],
            "improvable": r["improvable"],
            "applicable": r["applicable"],
            "prev_rate": prev_rates[r["step_id"]],
            "peer_median": medians.get(r["step_id"]),
        }
        for r in engine.step_rates(window_rows, steps)
    ]
    # No peer tie-break: the Head of Sales column and the messages (rep_focus) choose the
    # focus without it, so every surface names the same step. peer_median is still shown.
    chosen = engine.choose_focus(prev_week, steps)
    if chosen:
        chosen = {**chosen, "peer_median": medians.get(chosen["step_id"])}
    if chosen:
        definition = next(s for s in steps if str(s["step_id"]) == chosen["step_id"])
        peer_rows = [r for rows in ctx["peers"].values() for r in rows]
        body["focus"] = {
            "step_id": chosen["step_id"],
            "label": chosen["label"],
            "criterion": str(definition.get("criterion") or ""),
            "example": _example_for(definition, peer_rows),
            "why": {k: chosen[k] for k in ("rate", "applicable", "missing", "peer_median")},
            **engine.focus_progress(this_week, definition, ctx["week_start"]),
        }
    body["conversion"] = engine.conversion_split(ctx["own"], ctx["flow"])
    return body


_CALLS_WEEKS = STEP_WINDOW_WEEKS
_MAX_CALLS = 50


def _type_labels(supabase, company_id: str) -> dict[str, str]:
    """The company's own names for its interaction types; catalog types fall back to the app's."""
    try:
        from app.services.playbooks.repository import get_playbook_repository

        types = get_playbook_repository().list_types(company_id, include_draft=False)
    except Exception:
        return {}
    return {key: str(row.get("label")) for key, row in types.items() if row.get("label")}


@router.get("/coaching/me/calls")
async def get_my_coaching_calls(
    type_key: Optional[str] = Query(None, alias="type", max_length=64),
    membership: Membership = Depends(get_membership),
    supabase=Depends(get_supabase),
):
    """The rep's coaching over the last _CALLS_WEEKS weeks, one interaction type at a time, only
    against their own playbook: every step they slipped on and every objection they were given, each
    with the calls it happened in, and the record of their conversations step by step."""
    window_start = _week_starts(_CALLS_WEEKS)[0]
    _, week_end = madrid_week_bounds()
    memos = reads.load_memos(supabase, membership.company_id, [membership.user_id], start=window_start)
    rows = [row for row in _rows_of(memos) if row["motion"] and row["motion"] != INTERNAL_KEY]
    playbooks: dict[str, dict] = {}

    def playbook_for(motion: str) -> dict:
        if motion not in playbooks:
            playbooks[motion] = reads.load_published_playbook(supabase, membership.company_id, motion)
        return playbooks[motion]

    recent = _in_window(rows, window_start, week_end)
    counts: dict[str, int] = {}
    for row in recent:
        if row["is_conversation"]:
            counts[row["motion"]] = counts.get(row["motion"], 0) + 1
    # The types the rep had conversations of, most first; with none yet, the one their role is coached on.
    types = [m for m in sorted(counts, key=lambda m: (-counts[m], m)) if playbook_for(m)["published"]]
    if not types:
        flow = resolve_flow(membership.sales_role, recent, published_flows(playbook_for))
        fallback = motion_for_flow(flow, recent, playbook_for)
        if playbook_for(fallback)["published"]:
            types = [fallback]
    chosen = type_key if type_key in types else (types[0] if types else None)
    labels = _type_labels(supabase, membership.company_id) if types else {}
    body: dict = {
        "types": [{"key": m, "label": labels.get(m), "conversations": counts.get(m, 0)} for m in types],
        "type": chosen,
        "window_weeks": _CALLS_WEEKS,
        "conversations": 0,
        "slipped_steps": [],
        "objections": [],
        "calls": [],
    }
    if chosen is None:
        return body
    own = [row for row in rows if row["motion"] == chosen]
    window = _in_window(own, window_start, week_end)
    conversations = sorted((r for r in window if r["is_conversation"]), key=lambda r: r["observed_at"], reverse=True)
    body["conversations"] = len(conversations)
    playbook = playbook_for(chosen)
    # Everything to go through one by one: each slipped step and each objection, with its calls.
    body["slipped_steps"] = engine.slipped_steps(window, playbook["steps"])
    body["objections"] = engine.objection_breakdown(window, playbook["entries"])
    calls: list[dict] = []
    for row in conversations:
        part = engine.adherence_part(row) or {}
        calls.append({
            "memo_id": row["memo_id"],
            "observed_at": row["observed_at"],
            "duration_s": row["duration_s"],
            "summary_line": row["summary_line"],
            "meeting_agreed": row["meeting_agreed"],
            "done": part.get("met_steps", 0),
            "applicable": part.get("met_steps", 0) + part.get("missed_steps", 0),
            "slips": engine.call_slips(row),  # empty: nothing to improve in this one
        })
    body["calls"] = calls[:_MAX_CALLS]
    return body


class BetterReplyRequest(BaseModel):
    """One occurrence of Coaching's "En qué mejorar": a step the rep slipped on or an objection they were given."""

    type: str = Field(..., max_length=64)
    kind: Literal["step", "objection"]
    key: str = Field(..., max_length=120)
    memo_id: str = Field(..., max_length=64)
    # What the call says about this moment; the playbook text comes from the server, never from here.
    quote: Optional[str] = Field(default=None, max_length=600)
    response: Optional[str] = Field(default=None, max_length=600)
    reason: Optional[str] = Field(default=None, max_length=600)


@router.post("/coaching/me/better-reply")
async def post_better_reply(
    body: BetterReplyRequest,
    membership: Membership = Depends(get_membership),
    supabase=Depends(get_supabase),
):
    """The line the rep could have said at that moment, written from their playbook and "Vuestra
    empresa". `say` is null when the playbook gives nothing to base it on: the screen says so rather than
    showing something made up. 502 when the model failed (nothing is stored; try again)."""
    memo = _require_readable_memo(supabase, membership, body.memo_id)
    if str(memo.get("user_id") or "") != membership.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memo no encontrado")
    playbook = reads.load_published_playbook(supabase, membership.company_id, body.type)
    if body.kind == "step":
        step = next((s for s in playbook["steps"] if str(s.get("step_id")) == body.key), None)
        base = better.playbook_text_for_step(step) if step else None
    else:
        answer = engine._objection_answers(playbook["entries"]).get(body.key)
        base = better.playbook_text_for_objection(answer, engine.objection_entry(playbook["entries"], body.key)) if answer else None
    if not base:
        return {"say": None, "reason": "no_playbook_answer"}
    from app.services.copilot.load_grounding import load_company_knowledge
    from app.services.copilot.prompts import format_company_knowledge

    knowledge = format_company_knowledge(
        load_company_knowledge(supabase, company_id=membership.company_id),
        call_text=f"{body.quote or ''} {body.response or ''}",
    )
    try:
        rows = supabase.table("memos").select("transcript").eq("id", body.memo_id).execute().data or []
    except Exception:
        rows = []  # the line is then written from the quote alone
    messages = better.build_messages(
        kind=body.kind, playbook_text=base, said=body.quote, reply=body.response, reason=body.reason, knowledge=knowledge,
        excerpt=better.excerpt((rows[0] if rows else {}).get("transcript"), body.quote),
    )
    try:
        say = await better.better_reply(messages, cache_key=f"{membership.company_id}:{body.type}:{body.kind}:{body.key}:{body.memo_id}")
    except Exception:
        logging.getLogger(__name__).warning("coaching better-reply failed", exc_info=True)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="No se pudo escribir la respuesta") from None
    return {"say": say, "reason": None if say else "no_playbook_answer"}
