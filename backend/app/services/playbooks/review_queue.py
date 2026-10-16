"""The improvement queue and the numbers behind it: which approved answers keep failing in real calls, how much of what
customers raise already has an approved answer, and the later, bounded batch that judges the cards of finished calls.

Nothing here runs when a call ends. `refresh_outcomes` reads what is already stored (the live-help log, the call and its
post-call reading) a few cards at a time, so it can be called from a button, a schedule or a script without ever
competing with the post-call process. An answer reaches the queue only after MIN_CASES failing cases in FAIL_DAYS days.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.services.company import Membership
from app.services.playbooks.assistant import AssistantError, draft_content, edit_draft
from app.services.playbooks.assistant_store import AssistantStore
from app.services.playbooks.outcomes import MIN_CASES, outcome_for_event, ready_for_judging, success_stats
from app.services.playbooks.repository import PlaybookRepository
from app.services.playbooks.trial import _find_objection, activate, apply_verdict
from app.services.playbooks.versions import parse_ts

logger = logging.getLogger(__name__)

FAIL_DAYS = 30
COVERAGE_DAYS = 28
BATCH = 40
CONCURRENCY = 4
EVENT_SCAN = 500
MEMO_CHUNK = 20
_EVENT_COLUMNS = "id,created_at,sales_motion_key,latest_turn,objection_type,entry_id,is_objection,source_id,say_this,capture_id"
_USED = ("used", "adapted")
_FAILING = ("failed", "unused")


def case_mark(row: dict) -> str:
    """success | failed | unused | unknown for one verdict. A suggestion the rep did not say is `unused`; one they said
    that did not settle it is `failed`; anything that could not be read is `unknown` and never counts as a success."""
    used, resolved = row.get("used"), row.get("resolved")
    if used in _USED:
        return {"resolved": "success", "not_resolved": "failed"}.get(str(resolved), "unknown")
    return "unused" if used == "not_used" else "unknown"


def _now(now: Optional[datetime]) -> datetime:
    return now or datetime.now(timezone.utc)


def _within(rows: list[dict], field: str, days: int, now: Optional[datetime]) -> list[dict]:
    floor = _now(now) - timedelta(days=days)
    kept = []
    for row in rows:
        seen = parse_ts(row.get(field))
        if seen is not None and seen >= floor:
            kept.append(row)
    return kept


def failing_by_answer(outcomes: list[dict], *, min_cases: int = MIN_CASES, days: int = FAIL_DAYS, now: Optional[datetime] = None) -> list[dict]:
    """The approved answers whose cards failed at least `min_cases` times in the last `days` days, worst first ->
    [{answer_key, sales_motion_key, failing, total, cases, marks}]. An answer belongs to one call type: the price answer
    of "discovery" and the one of "closing" are counted apart. A failing case is a suggestion the rep did not say or one
    that did not settle it. `marks` has one entry per judged card of the answer, so the screen can draw them; `cases`
    only the failing ones. Cards with no approved answer behind them are a gap in the playbook, not a failing answer,
    and are left out."""
    by_answer: dict[tuple[Optional[str], str], list[dict]] = {}
    for row in _within(outcomes, "observed_at", days, now):
        if row.get("source_id"):
            by_answer.setdefault((row.get("sales_motion_key"), str(row["source_id"])), []).append(row)
    groups = []
    for (motion, key), rows in by_answer.items():
        marks = [case_mark(row) for row in rows]
        cases = [row for row, mark in zip(rows, marks) if mark in _FAILING]
        if len(cases) >= min_cases:
            groups.append({
                "answer_key": key, "sales_motion_key": motion, "failing": len(cases), "total": len(rows), "cases": cases, "marks": marks,
            })
    groups.sort(key=lambda group: (-group["failing"], group["sales_motion_key"] or "", group["answer_key"]))
    return groups


def coverage_stats(events: list[dict], *, days: int = COVERAGE_DAYS, min_cases: int = MIN_CASES, now: Optional[datetime] = None) -> dict:
    """What customers raised in the last `days` days and how much of it had an approved answer ->
    {detected, answered, rate}. The rate is None below `min_cases`: two cases say nothing."""
    raised = [e for e in _within(events, "created_at", days, now) if e.get("is_objection")]
    answered = sum(1 for e in raised if e.get("source_id"))
    return {"detected": len(raised), "answered": answered, "rate": answered / len(raised) if len(raised) >= min_cases else None}


def moments_by_answer(moments: list[dict], outcomes: list[dict], *, now: Optional[datetime] = None) -> list[dict]:
    """The open moments of the queue grouped by the answer they are about, each with that answer's numbers ->
    [{answer_key, sales_motion_key, failing, total, marks, stats, moments}], the answer that failed most first."""
    window = _within(outcomes, "observed_at", FAIL_DAYS, now)
    grouped: dict[tuple[Optional[str], str], list[dict]] = {}
    for moment in moments:
        if moment.get("entry_id"):
            grouped.setdefault((moment.get("sales_motion_key"), str(moment["entry_id"])), []).append(moment)
    groups = []
    for (motion, key), items in grouped.items():
        rows = [row for row in window if row.get("source_id") == key and row.get("sales_motion_key") == motion]
        marks = [case_mark(row) for row in rows]
        groups.append({
            "answer_key": key, "sales_motion_key": motion, "failing": sum(1 for mark in marks if mark in _FAILING), "total": len(rows),
            "marks": marks, "stats": success_stats(rows), "moments": items,
        })
    groups.sort(key=lambda group: (-group["failing"], group["sales_motion_key"] or "", group["answer_key"]))
    return groups


def refresh_moments(store: AssistantStore, company_id: str, groups: list[dict]) -> int:
    """Copies the failing cases to the improvement queue (the live-help log is purged at 90 days), once each: a case that
    was queued before, even if the Head of Sales already dealt with it, is not queued again. -> how many were added."""
    known = {str((moment.get("outcome") or {}).get("event_id")) for moment in store.list_moments(company_id)}
    added = 0
    for group in groups:
        for case in group["cases"]:
            event_id = str(case["event_id"])
            if event_id in known:
                continue
            store.add_moment(company_id, {
                "source": "real", "sales_motion_key": case.get("sales_motion_key"), "entry_id": group["answer_key"],
                "objection_type": case.get("objection_type"), "client_text": case.get("client_text") or "",
                "suggestion_text": case.get("suggestion_text"), "rep_text": case.get("rep_text"),
                "outcome": {"event_id": event_id, "used": case.get("used"), "resolved": case.get("resolved"), "mark": case_mark(case)},
            })
            known.add(event_id)
            added += 1
    return added


def _candidate_events(supabase: Any, company_id: str, since: str) -> list[dict]:
    """The company's live-help cards about an objection or a doubt since `since` that belong to a call, newest first."""
    try:
        result = (
            supabase.table("live_assist_events").select(_EVENT_COLUMNS)
            .eq("company_id", company_id).eq("kind", "suggest").eq("is_objection", True).gte("created_at", since)
            .order("created_at", desc=True).limit(EVENT_SCAN).execute()
        )
    except Exception as exc:
        logger.warning("live-help log not read for outcomes: %s", type(exc).__name__)
        return []
    return [e for e in (getattr(result, "data", None) or []) if e.get("capture_id")]


def _memos(supabase: Any, company_id: str, ids: list[str]) -> dict[str, dict]:
    try:
        result = supabase.table("memos").select("id,transcript,extraction").eq("company_id", company_id).in_("id", ids).execute()
    except Exception as exc:
        logger.warning("calls not read for outcomes: %s", type(exc).__name__)
        return {}
    return {str(m["id"]): m for m in getattr(result, "data", None) or []}


async def refresh_outcomes(
    store: AssistantStore, supabase: Any, company_id: str, *, limit: int = BATCH, days: int = COVERAGE_DAYS,
    llm: Any = None, now: Optional[datetime] = None,
) -> int:
    """Judges up to `limit` live-help cards that are ready (their call is closed and read) and were never judged ->
    how many were judged. Call it again for the next batch. Cards are judged a few at a time; a card the model could
    not read is stored as unknown rather than lost, and the Head of Sales can still correct it."""
    since = (_now(now) - timedelta(days=days)).isoformat()
    # supabase-py is synchronous: every read and write goes through a thread so a batch never holds the event loop.
    events = await asyncio.to_thread(_candidate_events, supabase, company_id, since)
    judged = await asyncio.to_thread(store.judged_event_ids, company_id, [str(e["id"]) for e in events])
    pending = [e for e in events if str(e["id"]) not in judged]
    ready: list[tuple[dict, dict]] = []
    for start in range(0, len(pending), MEMO_CHUNK):
        if len(ready) >= limit:
            break
        chunk = pending[start : start + MEMO_CHUNK]
        memos = await asyncio.to_thread(_memos, supabase, company_id, sorted({str(e["capture_id"]) for e in chunk}))
        for event in chunk:
            memo = memos.get(str(event["capture_id"]))
            if len(ready) < limit and ready_for_judging(event, memo, now=now):
                ready.append((event, memo))
    gate = asyncio.Semaphore(CONCURRENCY)

    async def judge(event: dict, memo: dict) -> None:
        async with gate:
            verdict = await outcome_for_event(event, memo, llm=llm)
        await asyncio.to_thread(store.upsert_outcome, company_id, verdict)

    await asyncio.gather(*(judge(event, memo) for event, memo in ready))
    return len(ready)


# --- what the Head of Sales sees and does ---------------------------------------------------------------------

# queue action -> the trial verdict that edits the draft the same way ("keep" edits nothing)
_EDITS = {"correct": "corrected", "branch": "branch", "new_objection": "own"}


def answer_of(repository: PlaybookRepository, company_id: str, motion: str, answer_key: str) -> Optional[dict]:
    """What the approved answer says now (its draft, else the published one) -> {category, label, guidance}; None when it is gone."""
    content, _ = draft_content(repository, company_id, motion)
    found = _find_objection(content.get("objections") or [], answer_key)
    if found is None:
        return None
    return {"category": found.get("category"), "label": found.get("label"), "guidance": found.get("guidance")}


def _public_moment(moment: dict) -> dict:
    outcome = moment.get("outcome") or {}
    return {
        "id": moment["id"], "event_id": outcome.get("event_id"), "client_text": moment.get("client_text"),
        "suggestion_text": moment.get("suggestion_text"), "rep_text": moment.get("rep_text"), "mark": outcome.get("mark") or "unknown",
    }


def pending_publish(store: AssistantStore, repository: PlaybookRepository, company_id: str) -> list[str]:
    """The call types the queue changed whose draft is not published yet."""
    touched = {str((m.get("outcome") or {}).get("motion")) for m in store.list_moments(company_id, status="corrected")}
    types = repository.list_types(company_id, include_draft=True)
    return sorted(key for key in touched if (types.get(key) or {}).get("has_draft"))


def public_queue(store: AssistantStore, repository: PlaybookRepository, company_id: str, default_motion: str, *, now: Optional[datetime] = None) -> dict:
    """The queue as the screen shows it -> {groups: [{answer_key, sales_motion_key, failing, total, marks, stats, answer, moments}],
    publish: [call types with changes to publish]}."""
    groups = moments_by_answer(store.list_moments(company_id, status="open"), recent_outcomes(store, company_id, now=now), now=now)
    shown = []
    for group in groups:
        motion = group["sales_motion_key"] or default_motion
        shown.append({**group, "answer": answer_of(repository, company_id, motion, group["answer_key"]), "moments": [_public_moment(m) for m in group["moments"]]})
    return {"groups": shown, "publish": pending_publish(store, repository, company_id)}


def answer_floors(store: AssistantStore, company_id: str) -> dict[tuple[Optional[str], str], datetime]:
    """When each answer (per call type) was last corrected from the queue. What happened before ran against the old wording."""
    floors: dict[tuple[Optional[str], str], datetime] = {}
    for moment in store.list_moments(company_id, status="corrected"):
        at = parse_ts(moment.get("resolved_at"))
        if at is None or not moment.get("entry_id"):
            continue
        key = (moment.get("sales_motion_key"), str(moment["entry_id"]))
        if key not in floors or at > floors[key]:
            floors[key] = at
    return floors


def recent_outcomes(store: AssistantStore, company_id: str, *, now: Optional[datetime] = None, after_fixes: bool = False) -> list[dict]:
    """The verdicts of the last FAIL_DAYS days, the window the queue and the numbers are read over. With `after_fixes` the
    cards of an answer from before the Head of Sales last corrected it are left out: a fixed answer starts again, it is
    not flagged for a month on what its old wording did. It decides what ENTERS the queue and the weekly report; the cases
    already waiting in the queue keep showing the whole window."""
    rows = store.list_outcomes(company_id, since=(_now(now) - timedelta(days=FAIL_DAYS)).isoformat())
    if not after_fixes:
        return rows
    floors = answer_floors(store, company_id)
    kept = []
    for row in rows:
        floor = floors.get((row.get("sales_motion_key"), str(row.get("source_id") or "")))
        seen = parse_ts(row.get("observed_at"))
        if floor is not None and seen is not None and seen <= floor:
            continue
        kept.append(row)
    return kept


def judged_stats(store: AssistantStore, company_id: str, *, now: Optional[datetime] = None) -> dict:
    """The numbers of judged calls -> {success: success_stats of the last COVERAGE_DAYS days, queue: {answers, cases}}."""
    outcomes = recent_outcomes(store, company_id, now=now)
    groups = moments_by_answer(store.list_moments(company_id, status="open"), outcomes, now=now)
    return {
        "success": success_stats(_within(outcomes, "observed_at", COVERAGE_DAYS, now)),
        "queue": {"answers": len(groups), "cases": sum(len(group["moments"]) for group in groups)},
    }


def act_on_moment(
    store: AssistantStore, repository: PlaybookRepository, company_id: str, moment_id: str, action: str, *,
    text: Optional[str] = None, when: Optional[str] = None, default_motion: str = "discovery", lang: str = "es",
) -> dict:
    """keep | correct | branch | new_objection on one case of the queue -> the moment saved. The three that change the answer edit
    the draft (never the published playbook) the way the trial does and remember which call type changed; an answer that does
    not fit raises ValueError and the case stays open. AssistantError: moment_not_found | moment_closed."""
    moment = store.get_moment(company_id, moment_id)
    if moment is None:
        raise AssistantError("moment_not_found")
    if moment.get("status") != "open":
        raise AssistantError("moment_closed")
    outcome = dict(moment.get("outcome") or {})
    if action == "keep":
        return store.update_moment(company_id, moment_id, status="kept")
    motion = moment.get("sales_motion_key") or default_motion
    case = {"client_text": moment.get("client_text") or ""}
    entry_id, verdict = moment.get("entry_id"), _EDITS[action]
    edit_draft(repository, company_id, motion, lambda content: apply_verdict(content, case, entry_id, verdict, text, when=when), lang=lang)
    return store.update_moment(company_id, moment_id, status="corrected", outcome={**outcome, "motion": motion, "action": action})


def publish_queue_changes(store: AssistantStore, repository: PlaybookRepository, membership: Membership) -> dict:
    """Publishes the drafts the queue changed -> {published, failed}. Live help reads them on its next card."""
    return activate(repository, membership, pending_publish(store, repository, membership.company_id))


def correct_verdict(store: AssistantStore, company_id: str, event_id: str, resolved: str) -> dict:
    """The Head of Sales says whether the suggestion settled it, whatever the judge decided -> the outcome saved with
    `resolved_by = "admin"`. A queued case that no longer fails is closed. AssistantError: outcome_not_found."""
    outcome = store.get_outcome(company_id, event_id)
    if outcome is None:
        raise AssistantError("outcome_not_found")
    saved = store.upsert_outcome(company_id, {**outcome, "resolved": resolved, "resolved_by": "admin"})
    if case_mark(saved) not in _FAILING:
        for moment in store.list_moments(company_id, status="open"):
            if str((moment.get("outcome") or {}).get("event_id")) == str(event_id):
                store.update_moment(company_id, moment["id"], status="dismissed")
    return saved
