"""The slow producer of the live call assistant: PROGRESS (Conversación) and the recap (Resumen).

Progress is where the call is against the company's playbook: which steps the rep has done, what the prospect said about
each thing to find out (qualification), whether the goal is reached, and the one thing that matters most now. It follows the
points by 1-3 s. Identities are the ones the after-call reading uses (steps by step_id, data by criterion_id), and an item is
done only with a verbatim quote, so the memo's checklist and coaching can start from it.

The recap is computed on request, from the call alone, and stored nowhere.

Also here: the per-version aids (a few words per step, a question per data point, which steps are about delivery and stay
for coaching), generated once per published playbook version.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Any, Optional

from app.services.copilot import live_brain as brain
from app.services.copilot.live_models import LiveReading, LiveTurn

logger = logging.getLogger(__name__)

NOW_KINDS = {"step", "data", "goal"}
MISSING_MAX = 3
RECAP_LINES = 4
QUOTE_MAX = 200

PROGRESS_SYSTEM = f"""You are Vocify's live assist: the slow half of the brain of a live sales call. You read the whole call
against the company's playbook and write the call's PROGRESS: which steps the rep has done, what the prospect has said about
each thing the playbook says to find out, whether the goal is reached, and the ONE thing that matters most now.

{brain.PRINCIPLE}

{brain.DATES}

RULES FOR PROGRESS
- Evidence or nothing. A step is done only when the REP's own words (a "You:" line) do what its criterion asks: cite the turn
  ids in "turns" exactly as in the brackets (for example "t12") and copy the rep's words verbatim in "quote" (at most 25 words). A data point is found only when the OTHER SIDE
  said it (a "Them:" line): cite the turns, copy their words verbatim in "quote", and write "value" in at most 10 words in their
  terms. A goal is reached only when the call clearly got there (the day and time are agreed). Not enough? It is not done.
- Read the whole CALL, not just the window: something may have been done earlier.
- List only what is NEW in this reading. Never list an item CALL STATE already has as done or found, nor one the rep ticked or
  unticked by hand: those are the rep's.
- "now" is the one item that matters most now AND has something to say: a pending step, a piece of data to find out, or the goal.
  The playbook's order is the default; what the goal needs first comes first. Keep PREVIOUS NOW unless it is done, the rep
  ticked it, or the conversation has clearly moved to another step: then set "moved_on" to true. Never change it between two
  readings for no reason.
- "say" is the words the rep says next, in the prospect's language, at most 30 words: for a step, its example adapted to what
  this prospect just said; for data, a question that finds it out from their own words; for the goal, the concrete next step.
  Use only what they said and the playbook; no new facts about the company, no hour the call did not give. A step's example is
  another prospect's sentence: it may presume things this call has not shown (an earlier agreement, the prospect's role or
  team, their figures, their tools). Drop or turn into a question everything the CALL and EARLIER CALLS do not support, and
  never assert something about the prospect they did not say. Never leave a placeholder in it (X, [name], ...): write it out
  from the call, or ask a plain question.
- "missing" lists up to {MISSING_MAX} ids of pending items, most important first (the first is "now").
- If the playbook has no steps, only data and the goal are tracked: "steps" is [].

OUTPUT: only valid JSON, keys in this order:
{{"steps": [{{"id": step id, "turns": [turn ids], "quote": verbatim}}],
"data": [{{"id": criterion id, "turns": [turn ids], "value": string, "quote": verbatim}}],
"goal": {{"reached": boolean, "turns": [turn ids], "value": string, "quote": verbatim}} or null,
"now": {{"kind": "step"|"data"|"goal", "id": string, "moved_on": boolean, "say": string}} or null,
"missing": [ids]}}"""

RECAP_SYSTEM = f"""You are Vocify's live assist. The rep asked for a recap: the other side's situation up to now, in their words
where it matters (who they are, what they asked for, who decides, what they agreed).

RULES
- At most {RECAP_LINES} lines, each at most 18 words, in the language of the call, each a fact about THEM or the agreement. Order: oldest first.
- Only from the CALL below. Never from the playbook, the knowledge or the offer. Never invent a name, a number, a date or a role
  (call someone a CEO or founder only if they said so). Keep what they said exactly, including doubts and negations («no estoy tan
  contento» is not «muy contento»); a number that is garbled or corrected in the call is left out.
- Nothing to say yet? "lines" is [].
- Do not list what is unknown and do not coach: code adds what is missing.

OUTPUT: only valid JSON: {{"lines": [string]}}"""

AIDS_SYSTEM = """You prepare a company's live-call playbook for the rep's screen. For each STEP write "concept": what it asks of the
rep in at most 7 words, imperative, in the playbook's language (e.g. «Di por qué le llamas a él»), and "live": true when the step
is something to DO or ASK in the call, false when it is about HOW the rep talks (length, tone, delivery, e.g. «explain X in 30
seconds»): those stay for coaching after the call. For each DATA item write "question": the question a rep asks to find it out,
built from its good answer, in at most 20 words; null when it has no good answer. Use only the playbook's own words.

OUTPUT: only valid JSON: {"steps": {step id: {"concept": string, "live": boolean}}, "data": {criterion id: {"question": string or null}}}"""


def _state_block(req: LiveReading, snapshot: dict) -> str:
    progress = req.progress
    labels = brain.labels_of(snapshot)

    def names(ids: list[str]) -> str:
        return ", ".join(f"{i} ({labels.get(i, i)})" for i in ids) or "none"

    if progress is None:
        return "CALL STATE: nothing found yet.\nPREVIOUS NOW: none"
    prev = progress.now
    return (
        "CALL STATE\n"
        f"- Steps done: {names(progress.done_steps)}\n- Data found: {names(progress.known_data)}\n"
        f"- Goal reached: {'yes' if progress.goal_reached else 'no'}\n"
        f"- Ticked or unticked by the rep (theirs, never list): {names(progress.rep_ticked + progress.rep_unticked)}\n"
        f"PREVIOUS NOW: {f'{prev.kind} {prev.id}' if prev else 'none'}"
    )


def _live_snapshot(snapshot: dict, aids: Optional[dict]) -> dict:
    """The playbook without the steps that are only about delivery (they stay for coaching)."""
    hidden = {i for i, a in ((aids or {}).get("steps") or {}).items() if a.get("live") is False}
    if not hidden:
        return snapshot
    return {**snapshot, "steps": [s for s in snapshot.get("steps") or [] if s.get("step_id") not in hidden]}


def build_progress_prompt(req: LiveReading, ctx: brain.BrainContext, aids: Optional[dict]) -> str:
    snapshot = _live_snapshot(ctx.snapshot, aids)
    call_text = "\n".join(t.text for t in req.turns[-30:])
    context = brain.context_blocks(
        product_context=ctx.product_context, knowledge=None, history=ctx.history, call_text=call_text,
    )
    changed = "THE TYPE CHANGED IN THIS CALL: read everything again under this playbook.\n\n" if req.type_changed else ""
    asked = "THE REP ASKED WHAT TO DO NEXT: make sure \"now\" is current.\n\n" if req.reason == "preguntar" else ""
    return (
        f"CALL MODE: {req.call_mode}\nPREFERRED LANGUAGE HINT: {req.language}\n\n{context}\n\n"
        f"{brain.playbook_header(snapshot, req.sales_motion_key, req.type_label)}\n{brain.steps_block(snapshot)}\n\n"
        f"{brain.qualification_block(snapshot)}\n\n{ctx.today}\n\n"
        f"CALL (turn ids in brackets):\n{brain.transcript_block(req.turns)}\n\n"
        f"{_state_block(req, snapshot)}\n\n{changed}{asked}{brain.window_line(req.focus_from)}\n\nJSON only."
    )


def _step_ids(snapshot: dict, aids: Optional[dict]) -> list[str]:
    live = _live_snapshot(snapshot, aids)
    return [s["step_id"] for s in live.get("steps") or [] if isinstance(s, dict) and s.get("step_id")]


def _data_ids(snapshot: dict) -> list[str]:
    return [q["criterion_id"] for q in snapshot.get("qualification") or [] if isinstance(q, dict) and q.get("criterion_id")]


def finalize_progress(raw: Optional[dict], req: LiveReading, ctx: brain.BrainContext, aids: Optional[dict]) -> dict[str, Any]:
    by_id = brain.turns_by_id(req.turns)
    snapshot = ctx.snapshot or {}
    progress = req.progress
    done = set(progress.done_steps) if progress else set()
    known = set(progress.known_data) if progress else set()
    rep = set((progress.rep_ticked + progress.rep_unticked) if progress else [])
    steps_all, data_all = _step_ids(snapshot, aids), _data_ids(snapshot)
    guards: dict[str, int] = {}

    def drop(reason: str) -> None:
        guards[reason] = guards.get(reason, 0) + 1

    steps: list[dict] = []
    for item in (raw or {}).get("steps") or []:
        sid = str((item or {}).get("id") or "") if isinstance(item, dict) else ""
        if sid not in steps_all or sid in done or sid in rep or any(s["id"] == sid for s in steps):
            continue
        turn_ids = brain.real_turn_ids(item.get("turns"), by_id, who="you")
        if not brain.is_quote_of(item.get("quote"), turn_ids, by_id):
            turn_ids = brain.locate_quote(item.get("quote"), req.turns, "you")[-2:]
        if not turn_ids:
            drop("step_without_evidence")
            continue
        steps.append({"id": sid, "status": "done", "by": "brain", "quote": brain._clip(item["quote"], QUOTE_MAX), "turn_ids": turn_ids})

    data: list[dict] = []
    for item in (raw or {}).get("data") or []:
        cid = str((item or {}).get("id") or "") if isinstance(item, dict) else ""
        if cid not in data_all or cid in known or cid in rep or any(d["id"] == cid for d in data):
            continue
        turn_ids = brain.real_turn_ids(item.get("turns"), by_id, who="them")
        value = brain._clip(item.get("value"), 100)
        if not brain.is_quote_of(item.get("quote"), turn_ids, by_id):
            turn_ids = brain.locate_quote(item.get("quote"), req.turns, "them")[-2:]
        if not turn_ids or not value:
            drop("data_without_evidence")
            continue
        data.append({
            "id": cid, "value": value, "quote": brain._clip(item["quote"], QUOTE_MAX), "turn_ids": turn_ids, "reread": req.type_changed,
        })

    goal = None
    raw_goal = (raw or {}).get("goal")
    if isinstance(raw_goal, dict) and raw_goal.get("reached") is True and not (progress and progress.goal_reached) and "goal" not in rep:
        turn_ids = brain.real_turn_ids(raw_goal.get("turns"), by_id)
        if not brain.is_quote_of(raw_goal.get("quote"), turn_ids, by_id):
            turn_ids = brain.locate_quote(raw_goal.get("quote"), req.turns)[-2:]
        if turn_ids:
            goal = {
                "reached": True, "value": brain._clip(raw_goal.get("value"), 100) or None,
                "quote": brain._clip(raw_goal["quote"], QUOTE_MAX), "turn_ids": turn_ids,
            }
        else:
            drop("goal_without_evidence")

    done_now = done | {s["id"] for s in steps} | rep
    known_now = known | {d["id"] for d in data} | rep
    goal_now = bool(goal) or bool(progress and progress.goal_reached) or "goal" in rep
    has_goal = brain.goal_for(req.sales_motion_key) is not None

    def pending(kind: str, ident: str) -> bool:
        if kind == "step":
            return ident in steps_all and ident not in done_now
        if kind == "data":
            return ident in data_all and ident not in known_now
        return kind == "goal" and has_goal and not goal_now

    now = None
    raw_now = (raw or {}).get("now")
    previous = progress.now if progress else None
    if previous and pending(previous.kind, previous.id) and not (isinstance(raw_now, dict) and raw_now.get("moved_on") is True):
        # Ahora is stable: it changes only when it is done, ticked, or the conversation clearly moved.
        now = {"kind": previous.kind, "id": previous.id, "say": previous.say}
        if isinstance(raw_now, dict) and raw_now.get("id") != previous.id:
            drop("now_kept")
    if now is None and isinstance(raw_now, dict) and raw_now.get("kind") in NOW_KINDS and pending(raw_now["kind"], str(raw_now.get("id") or "")):
        say = " ".join(str(raw_now.get("say") or "").split())[:300]
        if say and brain.invented_numbers(say, brain.allowed_numbers(req, ctx)):
            drop("invented_number")
            say = ""
        now = {"kind": raw_now["kind"], "id": str(raw_now["id"]), "say": say or None}
    if now is None:
        first_step = next((i for i in steps_all if pending("step", i)), None)
        first_data = next((i for i in data_all if pending("data", i)), None)
        pick = ("step", first_step) if first_step else ("data", first_data) if first_data else ("goal", "goal") if pending("goal", "goal") else None
        if pick:
            now = {"kind": pick[0], "id": pick[1], "say": None}
    if now and not now.get("say") and now["kind"] == "step":
        example = next((s.get("example") for s in snapshot.get("steps") or [] if s.get("step_id") == now["id"]), None)
        # The step's own sentence, unless it carries another prospect's figures: then the step's name is all there is.
        if example and not brain.invented_numbers(example, brain.allowed_numbers(req, ctx)):
            now["say"] = brain._clip(example, 300)

    missing: list[str] = []
    for ident in ([now["id"]] if now else []) + [str(i) for i in (raw or {}).get("missing") or []]:
        kind = "step" if ident in steps_all else "data" if ident in data_all else "goal" if ident == "goal" else None
        if kind and pending(kind, ident) and ident not in missing:
            missing.append(ident)
    return {
        "has_playbook": True, "steps": steps, "data": data, "goal": goal, "now": now, "missing": missing[:MISSING_MAX],
        "guards": guards, "playbook_version_id": ctx.playbook_version_id,
    }


# ---------- per-version aids ----------

_aids: dict[str, dict] = {}
_aids_running: dict[tuple, "asyncio.Task"] = {}
AIDS_MAX = 200


def aids_key(snapshot: dict) -> str:
    """One entry per published version; the content is in the key too, so an edit never reads a stale phrase."""
    digest = hashlib.sha1(
        repr([(s.get("step_id"), s.get("label"), s.get("criterion")) for s in snapshot.get("steps") or []]
             + [(q.get("criterion_id"), q.get("label"), q.get("good")) for q in snapshot.get("qualification") or []]).encode()
    ).hexdigest()[:12]
    return f"{snapshot.get('version_id') or '-'}:{digest}"


def _clean_aids(raw: Optional[dict], snapshot: dict) -> Optional[dict]:
    if not isinstance(raw, dict):
        return None
    steps = {
        sid: {"concept": brain._clip(a.get("concept"), 60) or sid, "live": a.get("live") is not False}
        for sid, a in (raw.get("steps") or {}).items()
        if isinstance(a, dict) and sid in {s.get("step_id") for s in snapshot.get("steps") or []}
    }
    data = {
        cid: {"question": brain._clip(a.get("question"), 160) or None}
        for cid, a in (raw.get("data") or {}).items()
        if isinstance(a, dict) and cid in set(_data_ids(snapshot))
    }
    return {"steps": steps, "data": data}


def _aids_prompt(snapshot: dict) -> str:
    return f"{brain.steps_block(snapshot)}\n\n{brain.qualification_block(snapshot)}\n\nJSON only."


async def aids_for(snapshot: Optional[dict]) -> Optional[dict]:
    """The playbook's aids, generated once per version and kept in memory (persisting and editing them is open). A failed
    generation is None for this request (progress then works without them) and is tried again by the next."""
    if not snapshot or not (snapshot.get("steps") or snapshot.get("qualification")):
        return None
    key = aids_key(snapshot)
    if key in _aids:
        return _aids[key]
    # One generation in flight per version and event loop (a task cannot be awaited from another loop).
    running_key = (key, id(asyncio.get_running_loop()))
    task = _aids_running.get(running_key)
    if task is None:
        async def generate() -> Optional[dict]:
            raw, meta = await brain.complete_json(AIDS_SYSTEM, _aids_prompt(snapshot), kind="aids")
            cleaned = _clean_aids(raw, snapshot)
            if cleaned is None:
                logger.warning("live brain: aids for %s failed: %s", key, meta.get("error"))
                return None
            if len(_aids) >= AIDS_MAX:
                _aids.pop(next(iter(_aids)))
            _aids[key] = cleaned
            return cleaned

        task = asyncio.ensure_future(generate())
        _aids_running[running_key] = task
        task.add_done_callback(lambda _t: _aids_running.pop(running_key, None))
    try:
        return await asyncio.shield(task)
    except Exception:
        logger.warning("live brain: aids for %s failed", key, exc_info=True)
        return None


# ---------- the producers ----------


async def read_progress(req: LiveReading, ctx: brain.BrainContext) -> dict[str, Any]:
    cursor = brain.cursor_of(req.turns)
    base = {"type": "result", "producer": "progress", "state_version": req.state_version, "cursor": cursor,
            "playbook": {"key": req.sales_motion_key, "name": req.type_label} if ctx.snapshot else None}
    if not ctx.snapshot:
        return {**base, "has_playbook": False, "steps": [], "data": [], "goal": None, "now": None, "missing": [], "aids": None, "guards": {}}
    if not req.turns or (req.reason not in {"responder", "preguntar", "resumen"} and not req.type_changed and req.cursor and req.cursor == cursor):
        return {**base, "has_playbook": True, "steps": [], "data": [], "goal": None, "now": None, "missing": [], "aids": None,
                "skipped": "no_new_words" if req.turns else "empty", "guards": {}}
    aids = await aids_for(ctx.snapshot)
    prompt = build_progress_prompt(req, ctx, aids)
    raw, meta = await brain.complete_json(PROGRESS_SYSTEM, prompt, kind="progress")
    if raw is None:
        return {"type": "error", "message": meta.get("error") or "no answer", "producer": "progress"}
    return {**base, **finalize_progress(raw, req, ctx, aids), "aids": aids, "model": meta["model"], "latency_ms": meta["latency_ms"]}


def finalize_recap(raw: Optional[dict], turns: list[LiveTurn], ctx: brain.BrainContext, req: LiveReading) -> dict[str, Any]:
    allowed = brain.numbers_in(" ".join(t.text for t in turns))
    guards = 0
    lines: list[str] = []
    for line in (raw or {}).get("lines") or []:
        text = " ".join(str(line or "").split())
        if not text:
            continue
        # An invented figure is the one lie a summary can tell in code-checkable form: every number must be in the call.
        if brain.invented_numbers(text, allowed):
            guards += 1
            continue
        lines.append(brain._clip(text, 160))
    snapshot = ctx.snapshot or {}
    progress = req.progress
    found = set((progress.known_data if progress else []) + (progress.rep_ticked if progress else []))
    unknown = [
        " ".join(str(q.get("label") or q["criterion_id"]).split())
        for q in snapshot.get("qualification") or []
        if isinstance(q, dict) and q.get("criterion_id") and q["criterion_id"] not in found
    ]
    return {"lines": lines[:RECAP_LINES], "unknown": unknown, "guards": {"invented_number": guards} if guards else {}}


async def read_recap(req: LiveReading, ctx: brain.BrainContext) -> dict[str, Any]:
    upto = brain.turns_by_id(req.turns).get(req.up_to or "")
    turns = req.turns[: req.turns.index(upto) + 1] if upto else req.turns
    base = {"type": "result", "producer": "recap", "state_version": req.state_version, "up_to": turns[-1].id if turns else None}
    if not turns:
        return {**base, "lines": [], "unknown": [], "guards": {}}
    prompt = f"CALL MODE: {req.call_mode}\nPREFERRED LANGUAGE HINT: {req.language}\n\n{ctx.today}\n\nCALL (turn ids in brackets):\n{brain.transcript_block(turns)}\n\nJSON only."
    raw, meta = await brain.complete_json(RECAP_SYSTEM, prompt, kind="recap")
    if raw is None:
        return {"type": "error", "message": meta.get("error") or "no answer", "producer": "recap"}
    return {**base, **finalize_recap(raw, turns, ctx, req), "model": meta["model"], "latency_ms": meta["latency_ms"]}
