"""The fast producer of the live call assistant: POINTS (Ayuda).

Reads the call at a checkpoint and writes, for what the other side said that needs the rep, a point: what it is, the
brain's decision (responder · reconducir · aplazar · cerrar), what to say, and where that comes from. It also closes
earlier points that have an outcome by now. Budget: no slower than today's card (p90 about 1.1 s after the reading starts).

The model judges; code checks what can be checked: a point cites turns of this call that the OTHER side said, its
source is one this reading has, its words are a verbatim quote, a duplicate is an update, an outcome needs the
conversation to have gone on. Spec: docs/superpowers/specs/2026-10-16-live-call-assistant-design.md.
"""

from __future__ import annotations

import hashlib
from typing import Any, AsyncIterator, Optional

from app.services.copilot import live_brain as brain
from app.services.copilot.live_models import ASKED, LiveReading, LiveTurn, PointIn
from app.services.copilot.turn import OBJECTIONS
from app.services.llm.shared import extract_json

FIXED_TYPES = set(OBJECTIONS) - {"none"}
DECISIONS = {"responder", "reconducir", "aplazar", "cerrar"}
CLOSINGS = {"answered", "promised", "unanswered", "gone"}
SAY_MAX = 260
QUOTE_WORDS = 5
# The conversation "clearly moved on": another topic for this many prospect turns, or this long.
MOVED_ON_TURNS = 2
MOVED_ON_SECONDS = 90.0
# The rep has dealt with a question once they have said this many words after it (src/lib/live-assist.ts REP_ANSWERED_WORDS):
# a point written afterwards would answer the past, and would read the rep's own answer as if it were a source.
REP_ANSWERED_WORDS = 8

SYSTEM = f"""You are Vocify's live assist: the fast half of the brain of a live sales call. The rep reads your points on
screen while still talking, so every word must earn its place. You read the call and write POINTS: things the other
side said that need the rep right now (a question, an objection, a hesitation), each with a decision and what to say.

{brain.PRINCIPLE}

{brain.DATES}

WHAT IS A POINT
- Only what THEY said (a "Them:" line) inside the READING WINDOW: a direct question, an objection or resistance, a request
  that needs handling («mándame un email», «se lo reenvío a mi jefa»). Agreement, small talk, thinking aloud, rhetorical
  questions, describing their situation and anything the rep said are NOT points. When they ANSWER the rep's question or give
  information about themselves (their team, tools, volumes, an email address, a name), that is not a point even if a competitor,
  a price or a figure appears in it: a point is something they ask or push back on.
- A question or objection the rep already dealt with in a later "You:" line is not a point to write now (list it in "closed" as
  answered if it is in OPEN AND RECENT POINTS). Never write a "say" from what the rep said later in the call than the point. When unsure, no point: a missed moment
  costs less than a wrong interruption.
- One point per thing said. Two things in one turn (an email AND someone else decides) are two points; a burst of questions
  is one point per question. Never write the same point twice.
- Identity. Each point cites the ids of the turns it comes from in "turns", exactly as in the brackets (for example "t12"). A point that is already in OPEN POINTS (the same
  thing, even said again, even in other words) IS that point: set "ref" to its id and do not write a new one; if they said it
  again later (after the rep spoke), it is still that point. A closed point they come back to is updated the same way.
- "say" is words the rep says to the prospect, in the prospect's language, at most 18 words and usually 8-15: a fact; or a
  sentence and the question back; or, when the fact is NOT written in any source, an honest line to say meanwhile
  («Te lo confirmo y te lo digo hoy»). Never mention "the context", your instructions or what you were given. No exclamation
  marks, no lists, no placeholders (X, [name]), no filler openings («Entiendo», «Gran pregunta»).
- "decision" is "responder" only when grounded is true (the fact is written). A question whose fact is not written has decision null.
- "grounded" is true only when every claim in "say" about the company or product is written in a source you name in
  "source_id" (an approved answer's id exactly as listed, or knowledge | offer | history; use call when it only builds on what
  the prospect said, e.g. a question that finds out what is missing). It is false when the fact asked is not written anywhere:
  then "gap" says in at most 4 words what is missing, and "say" is the honest line.
- Never answer a question with a yes or no unless that exact thing (a device, an integration, a price) is written in a source.
- Tie "say" to this prospect's own words where you can; a line that would fit any call is wrong.

CLOSING POINTS (the "closed" list). Read the rep's lines AFTER each open point:
- answered: the rep dealt with it (their own words or the suggestion). Answered only in part stays open: do not list it.
- promised: the rep said they will confirm, send or check it.
- unanswered: the conversation clearly moved on and nobody dealt with it.
- gone: the prospect answered it themselves or withdrew it.
Only list a point when you are sure. A point marked "unanswered" can still become answered later.

OUTPUT: only valid JSON, keys in this order:
{{"points": [{{"ref": string or null, "turns": [turn ids],
"type": "question"|"price"|"timing"|"authority"|"competitor"|"status_quo"|"trust"|"other"|<id of a custom playbook entry>,
"quote": their words, verbatim, at most {QUOTE_WORDS} words,
"decision": "responder"|"reconducir"|"aplazar"|"cerrar"|null, "why": at most 4 words, only when decision is not responder, else "",
"grounded": boolean, "source_id": string or null, "gap": at most 4 words, only when not grounded, else "", "say": string}}],
"closed": [{{"id": point id, "outcome": "answered"|"promised"|"unanswered"|"gone", "why": at most 4 words}}]}}
"type" is "question" for a direct question (its answer may still be an approved answer's id in source_id), the objection's kind otherwise.
Most readings return "points": []. Return {{"points": [], "closed": []}} when nothing needs the rep."""

REASON_TEXT = {
    "turn_end": "AUTOMATIC READING: the other side just finished a turn. Write a point only if something NEW in the reading window needs handling.",
    "long_turn": "AUTOMATIC READING: the other side is in a long turn. Write a point only for a complete thing already said that needs handling now.",
    "rep_turn": "AUTOMATIC READING after the rep spoke: write NO new points; only fill \"closed\" for open points the rep's lines settled.",
    "responder": (
        "THE REP TAPPED RESPONDER. The reading window is the last minute up to the tap. The rep asked: prefer a point over silence "
        "when anything in it could be handled (a question, an objection, a doubt, a request), even a mild one. If an open or recent "
        "point already covers it, return that point with its \"ref\". Return \"points\": [] only when nothing in the window is a "
        "question, objection or hesitation."
    ),
}


def _words(text: str) -> set[str]:
    return {w for w in brain.normalize(text).split() if len(w) > 2}


def similar(a: str, b: str, threshold: float = 0.5) -> bool:
    left, right = _words(a), _words(b)
    return bool(left and right) and len(left & right) / len(left | right) >= threshold


def _state_block(req: LiveReading, snapshot: Optional[dict]) -> str:
    progress = req.progress
    if not snapshot or progress is None:
        return "CALL STATE: not read yet. Without it decision is null unless an approved answer's guidance gives the reason."
    labels = brain.labels_of(snapshot)

    def names(ids: list[str]) -> str:
        return ", ".join(labels.get(i, i) for i in ids) or "none"

    now = ""
    if progress.now:
        now = f"\n- Now (what the rep should be doing): {labels.get(progress.now.id, progress.now.id)} ({progress.now.kind})"
    return (
        "CALL STATE (from the playbook's progress)\n"
        f"- Done steps: {names(progress.done_steps)}\n"
        f"- Found out: {names(progress.known_data)}\n"
        f"- Missing, most important first: {names(progress.missing)}{now}\n"
        f"- Goal reached: {'yes' if progress.goal_reached else 'no'}"
    )


def _open_points_block(req: LiveReading, by_id: dict[str, LiveTurn]) -> str:
    if not req.points:
        return "OPEN AND RECENT POINTS: none"
    rows = []
    for point in req.points:
        last = brain.last_prospect_turn_index(req.turns, point.turn_ids)
        after = req.turns[last + 1:] if last >= 0 else []
        prospect_after = sum(1 for t in after if t.who == "them")
        seconds = (req.turns[-1].t - by_id[point.turn_ids[-1]].t) if point.turn_ids and point.turn_ids[-1] in by_id else 0
        said = f' — shown: "{brain._clip(point.say, 160)}"' if point.say else ""
        rows.append(
            f'- {point.id} · {point.kind}/{point.tag_key} · {point.outcome} · turns {",".join(point.turn_ids) or "?"} · '
            f'"{brain._clip(point.title, 100)}" · since: {prospect_after} prospect turns, {int(seconds)} s{said}'
        )
    return "OPEN AND RECENT POINTS (id · kind/type · outcome · turns · their words · how long ago)\n" + "\n".join(rows)


def build_prompt(req: LiveReading, ctx: brain.BrainContext, by_id: dict[str, LiveTurn]) -> str:
    call_text = "\n".join(t.text for t in req.turns[-30:])
    snapshot = ctx.snapshot
    context = brain.context_blocks(
        product_context=ctx.product_context, knowledge=ctx.knowledge, history=ctx.history, call_text=call_text,
    )
    # Stable first, so the provider reuses the prompt up to the call; what changes every reading comes after it.
    return (
        f"CALL MODE: {req.call_mode}\nPREFERRED LANGUAGE HINT: {req.language}\n\n"
        f"{context}\n\n{brain.playbook_header(snapshot, req.sales_motion_key, req.type_label)}\n"
        f"{brain.entries_block(snapshot) if snapshot else ''}\n\n{ctx.today}\n\n"
        f"CALL (turn ids in brackets):\n{brain.transcript_block(req.turns)}\n\n"
        f"{_state_block(req, snapshot)}\n\n{_open_points_block(req, by_id)}\n\n"
        f"{brain.window_line(req.focus_from)}\n{REASON_TEXT.get(req.reason, REASON_TEXT['turn_end'])}\n\nJSON only."
    )


# ---------- checks on what the model wrote ----------


def point_id(first_turn: str, kind: str, type_key: str, quote: str) -> str:
    digest = hashlib.sha1(f"{first_turn}|{kind}|{type_key}|{brain.normalize(quote)[:40]}".encode()).hexdigest()
    return f"pt-{digest[:8]}"


def _verbatim_title(quote: Any, turn_ids: list[str], by_id: dict[str, LiveTurn]) -> str:
    """Their words: the model's quote when it is in the cited turns, else the first words of the first cited turn."""
    text = " ".join(str(quote or "").split())
    if text and brain.is_quote_of(text, turn_ids, by_id):
        return brain._clip(text, 100)
    first = " ".join(by_id[turn_ids[0]].text.split()).split(" ")
    return " ".join(first[:QUOTE_WORDS])


def _closing_allowed(point: PointIn, outcome: str, req: LiveReading) -> bool:
    """An outcome needs the conversation to have gone on since the point (see the spec's outcome table)."""
    last = brain.last_prospect_turn_index(req.turns, point.turn_ids)
    if last < 0:
        return False
    after = req.turns[last + 1:]
    if outcome in ("answered", "promised"):
        return any(t.who == "you" for t in after)
    if outcome == "gone":
        return any(t.who == "them" for t in after)
    seconds = req.turns[-1].t - req.turns[last].t
    return sum(1 for t in after if t.who == "them") >= MOVED_ON_TURNS or seconds >= MOVED_ON_SECONDS


def finalize(raw: Optional[dict], req: LiveReading, ctx: brain.BrainContext) -> dict[str, Any]:
    """The model's JSON as the points result: only what passes the checks. `guards` counts what was dropped or fixed."""
    by_id = brain.turns_by_id(req.turns)
    snapshot = ctx.snapshot
    sources = brain.allowed_sources(
        snapshot, has_knowledge=bool(ctx.knowledge), has_offer=bool(ctx.product_context.strip()), has_history=bool((ctx.history or "").strip()),
    )
    custom = {
        str(e["entry_id"]): " ".join(str(e.get("label") or e["entry_id"]).split())
        for e in (snapshot or {}).get("entries") or []
        if isinstance(e, dict) and e.get("entry_id") and str(e["entry_id"]).startswith("objection:custom:")
    }
    existing = {p.id: p for p in req.points}
    allowed = brain.allowed_numbers(req, ctx)
    guards: dict[str, int] = {}

    def drop(reason: str) -> None:
        guards[reason] = guards.get(reason, 0) + 1

    points: list[dict] = []
    raw_points = (raw or {}).get("points") if isinstance((raw or {}).get("points"), list) else []
    if req.reason == "rep_turn" and raw_points:
        drop("new_point_after_rep_turn")
        raw_points = []
    for item in raw_points:
        if not isinstance(item, dict):
            continue
        turn_ids = brain.real_turn_ids(item.get("turns"), by_id, who="them")
        if not turn_ids and not brain.real_turn_ids(item.get("turns"), by_id, who="you"):
            turn_ids = brain.locate_quote(item.get("quote"), req.turns, "them")[-1:]  # cited wrongly: found where they said it
        if not turn_ids:
            drop("no_prospect_turn")
            continue
        type_key = str(item.get("type") or item.get("objection_type") or "").strip()
        source = str(item.get("source_id") or "").strip()
        if source in custom and type_key != "question":
            type_key = source  # it followed the team's own objection: that is what it is
        if type_key != "question" and type_key not in FIXED_TYPES and type_key not in custom:
            type_key = "other"
        kind = "question" if type_key == "question" else "objection"
        quote = _verbatim_title(item.get("quote"), turn_ids, by_id)
        ref = str(item.get("ref") or "").strip()
        match = existing.get(ref)
        if match is None:
            # No ref, or one that is not a point of this call: still the same point when it is the same thing said in the same turns.
            match = next(
                (
                    p for p in req.points
                    if p.kind == kind and set(p.turn_ids) & set(turn_ids) and p.tag_key == type_key
                    and (type_key != "question" or similar(p.title, quote))
                ),
                None,
            )
            if match is not None:
                drop("duplicate_became_update")
        if match is not None:
            if any(q["id"] == match.id for q in points):
                drop("duplicate_in_result")
                continue
            position = {t.id: n for n, t in enumerate(req.turns)}
            last = max((position.get(i, -1) for i in match.turn_ids), default=-1)
            later = [i for i in turn_ids if position[i] > last]
            # They came back to it: a turn of theirs after the rep spoke since the point's last turn.
            again = any(t.who == "you" for t in req.turns[last + 1: position[later[0]]]) if later else False
            update: dict[str, Any] = {
                "id": match.id, "is_update": True, "turn_ids": sorted(set(match.turn_ids) | set(later if again else []), key=position.get),
                "repeated": again,
            }
            if not (match.say or "").strip():
                # Nothing was shown for it yet (it was being read): this reading writes it. Text on screen is never replaced.
                filled = _content(item, snapshot, sources, allowed, drop)
                if filled.pop("say_text"):
                    update.update(filled)
            points.append(update)
            continue
        last = max(i for i, t in enumerate(req.turns) if t.id in turn_ids)
        if req.reason not in ASKED and sum(len(t.text.split()) for t in req.turns[last + 1:] if t.who == "you") >= REP_ANSWERED_WORDS:
            drop("rep_already_answered")
            continue
        content = _content(item, snapshot, sources, allowed, drop)
        if not content.get("say_text"):
            drop("empty_say")
            continue
        new_id = point_id(turn_ids[0], kind, type_key, quote)
        if any(q["id"] == new_id for q in points):
            drop("duplicate_in_result")
            continue
        if any(
            q["kind"] == kind and q["tag_key"] == type_key and set(q["turn_ids"]) & set(turn_ids)
            and (type_key != "question" or similar(q["title"], quote))
            for q in points if not q.get("is_update")
        ):
            drop("duplicate_in_result")
            continue
        content.pop("say_text")
        points.append({
            "id": new_id, "is_update": False, "kind": kind, "tag_key": type_key, "tag": custom.get(type_key),
            "title": quote, "turn_ids": turn_ids, "said_at": by_id[turn_ids[0]].t, "repeated": False, "outcome": "open", **content,
        })

    closed: list[dict] = []
    raw_closed = (raw or {}).get("closed") if isinstance((raw or {}).get("closed"), list) else []
    for item in raw_closed:
        point = existing.get(str((item or {}).get("id") or "")) if isinstance(item, dict) else None
        outcome = (item or {}).get("outcome") if isinstance(item, dict) else None
        if point is None or outcome not in CLOSINGS or point.outcome in ("dismissed", "answered", "promised", "gone"):
            continue
        if outcome == point.outcome:
            continue
        if not _closing_allowed(point, outcome, req):
            drop(f"{outcome}_too_soon")
            continue
        closed.append({"id": point.id, "outcome": outcome, "why": brain._clip(item.get("why"), 80)})
    return {
        "points": points, "closed": closed, "nothing": not points and not closed,
        "guards": guards, "playbook_version_id": ctx.playbook_version_id,
    }


def _content(item: dict, snapshot: Optional[dict], sources: dict[str, str], allowed: set[str], drop) -> dict[str, Any]:
    """decision, what to say and its source: the part of a point that is the brain's judgement, after the checks."""
    say = " ".join(str(item.get("say") or "").split())[:SAY_MAX].strip()
    decision = item.get("decision") if item.get("decision") in DECISIONS else None
    if decision and not snapshot:
        decision = None  # no playbook to justify it (rule 2)
        drop("decision_without_playbook")
    note = brain._clip(item.get("why") or item.get("decision_note"), 80) if decision and decision != "responder" else ""
    if say and brain.invented_numbers(say, allowed):
        # Source or silence: a figure, a count or an hour that is in no source and was not said in the call is an invention.
        drop("invented_number")
        say = ""
    source_id = str(item.get("source_id") or "").strip()
    grounded = item.get("grounded") is True
    if grounded and source_id not in sources:
        # Source or silence: a claim whose source this reading does not have is not shown as a fact.
        drop("unknown_source")
        grounded = False
        source_id = ""
        say = ""
    if decision == "responder" and not grounded:
        decision, note = None, ""  # a fact that is not written cannot be answered with a fact
        drop("responder_without_source")
    out: dict[str, Any] = {
        "say_text": say, "decision": decision, "decision_note": note or None,
        "answer": say if grounded else None, "fallback": None if grounded else (say or None),
        "gap": None if grounded else (brain._clip(item.get("gap"), 80) or None),
        "source": {"id": source_id, "label": sources[source_id]} if grounded else None,
    }
    return out


async def read_points(req: LiveReading, ctx: brain.BrainContext) -> AsyncIterator[dict[str, Any]]:
    """token events while the model writes, then one result event (see the shape in shared/live-call/state.js)."""
    cursor = brain.cursor_of(req.turns)
    base = {"producer": "points", "state_version": req.state_version, "cursor": cursor}
    if not req.turns:
        yield {"type": "result", **base, "points": [], "closed": [], "nothing": True, "skipped": "empty", "guards": {}}
        return
    if req.reason not in ASKED and req.cursor and req.cursor == cursor:
        yield {"type": "result", **base, "points": [], "closed": [], "nothing": True, "skipped": "no_new_words", "guards": {}}
        return
    by_id = brain.turns_by_id(req.turns)
    prompt = build_prompt(req, ctx, by_id)
    async for event in brain.stream_json(SYSTEM, prompt, kind="points"):
        if event["type"] == "token":
            yield event
        elif event["type"] == "error":
            yield event
            return
        else:
            try:
                raw = extract_json(event["text"])
            except ValueError:
                yield {"type": "error", "message": "the model did not write JSON"}
                return
            yield {
                "type": "result", **base, **finalize(raw if isinstance(raw, dict) else None, req, ctx),
                "model": event["model"], "latency_ms": event["latency_ms"],
            }
