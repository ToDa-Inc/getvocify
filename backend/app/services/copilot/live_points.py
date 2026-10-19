"""The fast producer of the live call assistant: POINTS (Ayuda).

Reads the call at a checkpoint and writes, for what the other side said that needs the rep, a point: what it is, the
brain's decision (responder · reconducir · aplazar · cerrar), what to say, and where that comes from. It also closes
earlier points that have an outcome by now. Budget: no slower than today's card (p90 about 1.1 s after the reading starts).

With the "Qué decir" view (`say_view`) a point may also be an opportunity to go deeper ("deepen": one question on something
important they said vaguely). Two asked readings write no points: "rewrite" (the same point from another angle of the same
source) and "ask_step" (one question for a pending step or data item). Responder with nothing to answer gives `next`, the
missing item that matters most and its question. Spec: docs/superpowers/specs/2026-10-20-live-say-view-build-contract.md §2.

The model judges; code checks what can be checked: a point cites turns of this call that the OTHER side said, its
source is one this reading has, its words are a verbatim quote, a duplicate is an update, an outcome needs the
conversation to have gone on. Spec: docs/superpowers/specs/2026-10-16-live-call-assistant-design.md.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, AsyncIterator, Optional

from app.services.copilot import live_brain as brain
from app.services.copilot import live_progress
from app.services.copilot.live_models import ASKED, LiveReading, LiveTurn, PointIn
from app.services.copilot.turn import OBJECTIONS
from app.services.llm.shared import extract_json

FIXED_TYPES = set(OBJECTIONS) - {"none"}
DECISIONS = {"responder", "reconducir", "aplazar", "cerrar"}
CLOSINGS = {"answered", "promised", "unanswered", "gone"}
# What appears on its own (spec, "Qué decir": one or two sentences, ~20 words). The prompt asks for less; this is the cap in code.
ANSWER_MAX_WORDS = 20
ANSWER_MAX_SENTENCES = 2
QUOTE_WORDS = 5
# The conversation "clearly moved on": another topic for this many prospect turns, or this long.
MOVED_ON_TURNS = 2
MOVED_ON_SECONDS = 90.0
# The rep has dealt with a question once they have said this many words after it (src/lib/live-assist.ts REP_ANSWERED_WORDS):
# a point written afterwards would answer the past, and would read the rep's own answer as if it were a source.
REP_ANSWERED_WORDS = 8
# A rewrite this close to a version already shown is the same line again.
REWRITE_SAME = 0.7
# A deepen point on a topic an earlier one already covered (their words or the question) is a variation, not a new one.
DEEPEN_SAME_TOPIC = 0.4
# Words too common to show that a question is built on what they said.
_COMMON = frozenset(
    "para pero porque como cuando donde esto esta este estas estos esos esas eso hace hacer hacen tiene tienen tengo tenemos "
    "sabes vale bueno pues entonces ahora tambien todo todos toda todas mucho mucha muchos muchas poco nada algo cosa cosas "
    "estan estamos somos sois eres creo digo dices verdad claro mira oye vamos venga with that this what have they your from".split()
)
# What "the last minutes" of the call are for a step's question.
STEP_WINDOW_S = 240.0
STEP_WINDOW_TURNS = (8, 30)

_SYSTEM = f"""You are Vocify's live assist: the fast half of the brain of a live sales call. The rep reads your points on
screen while still talking, so every word must earn its place. You read the call and write POINTS: things the other
side said that need the rep right now (a question, an objection, a hesitation), each with a decision and what to say.

{brain.PRINCIPLE}

{brain.DATES}

WHAT IS A POINT
- Only what THEY said (a "Them:" line) inside the READING WINDOW: a direct question, an objection or resistance, a request
  that needs handling («mándame un email», «se lo reenvío a mi jefa»). Agreement, small talk, thinking aloud, rhetorical
  questions, describing their situation and anything the rep said are NOT points{{deepen_exception}}. When they ANSWER the rep's question or give
  information about themselves (their team, tools, volumes, an email address, a name), that is not a point even if a competitor,
  a price or a figure appears in it: a point is something they ask or push back on.
- A question or objection the rep already dealt with in a later "You:" line is not a point to write now (list it in "closed" as
  answered if it is in OPEN AND RECENT POINTS). Never write a "say" from what the rep said later in the call than the point. When unsure, no point: a missed moment
  costs less than a wrong interruption.
- One point per thing said. Two things in one turn (an email AND someone else decides) are two points; a burst of questions
  is one point per question. Write them in the order they were said. Never write the same point twice.
- Identity. Each point cites the ids of the turns it comes from in "turns", exactly as in the brackets (for example "t12"). A point that is already in OPEN POINTS (the same
  thing, even said again, even in other words) IS that point: set "ref" to its id and do not write a new one; if they said it
  again later (after the rep spoke), it is still that point. A closed point they come back to is updated the same way.
  "ref" is only for the SAME request, question or objection said again. Something new they add, even about the same topic,
  is a new point: after «¿cuánto cuesta?», «y lo tiene que ver mi socio» is a new point (someone else decides), not a repeat.
- "say" is words the rep says to the prospect, in the prospect's language, at most 15 words, at most two short sentences: a fact; or a
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
{{deepen_block}}
CLOSING POINTS (the "closed" list). Read the rep's lines AFTER each open point:
- answered: the rep dealt with it (their own words or the suggestion). Answered only in part stays open: do not list it.{{deepen_closing}}
- promised: the rep said they will confirm, send or check it.
- unanswered: the conversation clearly moved on and nobody dealt with it.
- gone: the prospect answered it themselves or withdrew it.
Only list a point when you are sure. A point marked "unanswered" can still become answered later.

OUTPUT: only valid JSON, keys in this order:
{{"points": [{{"ref": string or null, "turns": [turn ids],
"type": "question"|"price"|"timing"|"authority"|"competitor"|"status_quo"|"trust"|"other"|<id of a custom playbook entry>{{deepen_type}},
"quote": their words, verbatim, at most {QUOTE_WORDS} words,
"decision": "responder"|"reconducir"|"aplazar"|"cerrar"|null, "why": at most 4 words, only when decision is not responder, else "",
"grounded": boolean, "source_id": string or null, "gap": at most 4 words, only when not grounded, else "", "say": string}}],
"closed": [{{"id": point id, "outcome": "answered"|"promised"|"unanswered"|"gone", "why": at most 4 words}}]}}
"type" is "question" for a direct question (its answer may still be an approved answer's id in source_id), the objection's kind otherwise.
Most readings return "points": []. Return {{"points": [], "closed": []}} when nothing needs the rep."""

DEEPEN_BLOCK = """
GO DEEPER (type "deepen")
- Besides questions and objections there is ONE more kind of point: they STATE something important about a topic the STEPS
  below care about (a pain, a problem, how they work today) but VAGUELY, with no cause, case or figure of their own («perdemos
  muchísimo tiempo», «el seguimiento es un caos»). Then write a point with "type": "deepen" whose "say" is ONE question that goes
  one rung deeper on the playbook's own ladder (una causa, un caso, una cifra: ask for the next of those they have NOT given),
  built from their own words, at most 15 words. "source_id" is "step:" + the id of the step it serves, "decision" null,
  "grounded" true, "gap" "".
- The question takes up THEIR words (the thing they named: «el seguimiento», «el copia y pega»), never a generic pain question.
- Never a deepen point: on ordinary sentences (agreement, small talk, their role or company, an answer that already has the
  detail, anything no step cares about); on what they say about OUR product, the demo or this call (that is feedback, not how
  they work); when they already gave a figure (hours, money, people, a count: that is information);
  when the rep is already following it up (a "You:" line after it digs into the same thing); when OPEN AND RECENT POINTS has a
  deepen point that is open or on the same topic (one question per topic); more than one per reading. A question or an
  objection always comes before a deepen point. When unsure, no deepen point: most turns have none.
"""

SYSTEM = _SYSTEM.replace("{deepen_exception}", "").replace("{deepen_block}", "").replace("{deepen_closing}", "").replace("{deepen_type}", "")
# The "Qué decir" view: the same rules plus the opportunity to go deeper.
SYSTEM_SAY = (
    _SYSTEM.replace("{deepen_exception}", " (except the GO DEEPER case below)").replace("{deepen_block}", DEEPEN_BLOCK)
    .replace("{deepen_closing}", " A deepen point is answered when the rep asked it, or something with the same aim, in their own words.")
    .replace("{deepen_type}", '|"deepen"')
)

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

NEXT_TEXT = (
    "\nIF \"points\" IS []: add the key \"next\": {{\"question\": string}}, ONE question the rep asks now to find out the PENDING ITEM "
    "below, built from what the prospect said in this call (their words), never asking what they already said, at most 15 words, "
    "in their language, no facts about the company, never presuming what the call does not show (an earlier agreement, a pilot, "
    "their tools or figures). When you write a point, \"next\" is null.\nPENDING ITEM: {item}"
)


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


def deepen_on(req: LiveReading, ctx: brain.BrainContext) -> bool:
    """The "go deeper" trigger: only on the say view, and only with playbook steps to serve (the playbook is the compass)."""
    return req.say_view and bool(ctx.snapshot and ctx.snapshot.get("steps"))


def _steps_line(snapshot: dict) -> str:
    """The steps as go deeper needs them: what each one is about, short (the full block with examples costs latency)."""
    rows = [
        f'- step:{step["step_id"]} · {brain._clip(step.get("label"), 60)} — {brain._clip(step.get("criterion"), 140)}'
        for step in snapshot.get("steps") or [] if isinstance(step, dict) and step.get("step_id")
    ]
    return "STEPS (source id · label — what it is about)\n" + "\n".join(rows)


def build_prompt(req: LiveReading, ctx: brain.BrainContext, by_id: dict[str, LiveTurn], item: Optional[dict] = None) -> str:
    call_text = "\n".join(t.text for t in req.turns[-30:])
    snapshot = ctx.snapshot
    context = brain.context_blocks(
        product_context=ctx.product_context, knowledge=ctx.knowledge, history=ctx.history, call_text=call_text,
    )
    steps = f"\n\n{_steps_line(snapshot)}" if deepen_on(req, ctx) else ""
    ask = REASON_TEXT.get(req.reason, REASON_TEXT["turn_end"])
    if req.reason == "responder" and item:
        ask += NEXT_TEXT.format(item=_item_line(item))
    # Stable first, so the provider reuses the prompt up to the call; what changes every reading comes after it.
    return (
        f"CALL MODE: {req.call_mode}\nPREFERRED LANGUAGE HINT: {req.language}\n\n"
        f"{context}\n\n{brain.playbook_header(snapshot, req.sales_motion_key, req.type_label)}\n"
        f"{brain.entries_block(snapshot) if snapshot else ''}{steps}\n\n{ctx.today}\n\n"
        f"CALL (turn ids in brackets):\n{brain.transcript_block(req.turns)}\n\n"
        f"{_state_block(req, snapshot)}\n\n{_open_points_block(req, by_id)}\n\n"
        f"{brain.window_line(req.focus_from)}\n{ask}\n\nJSON only."
    )


# ---------- pending items: Responder with nothing, and a step's question ----------


def _aids(snapshot: Optional[dict]) -> dict:
    """The playbook's aids if they were generated already (by a progress reading). Never generated here: these readings are fast."""
    return live_progress.cached_aids(snapshot) or {}


def pending_item(req: LiveReading, ctx: brain.BrainContext, kind: Optional[str] = None, ident: Optional[str] = None) -> Optional[dict]:
    """A pending step or data item of the playbook: {kind, id, label, detail, missing_parts, question}. With `kind` and `id`,
    that item (None if it is not in the playbook or already done); without them, the one that matters most now: the progress
    reading's "now" and "missing" picks first, then what the playbook says to find out, in its order, then its steps."""
    snapshot = ctx.snapshot or {}
    aids = _aids(snapshot)
    hidden = {i for i, a in (aids.get("steps") or {}).items() if a.get("live") is False}
    steps = {s["step_id"]: s for s in snapshot.get("steps") or [] if isinstance(s, dict) and s.get("step_id") and s["step_id"] not in hidden}
    data = {q["criterion_id"]: q for q in snapshot.get("qualification") or [] if isinstance(q, dict) and q.get("criterion_id")}
    progress = req.progress
    ticked = set(progress.rep_ticked) if progress else set()
    unticked = set(progress.rep_unticked) if progress else set()
    done = ((set(progress.done_steps) if progress else set()) | ticked) - unticked
    known = ((set(progress.known_data) if progress else set()) | ticked) - unticked

    def build(k: str, i: str) -> Optional[dict]:
        if k == "step" and i in steps and i not in done:
            step = steps[i]
            parts = (aids.get("steps") or {}).get(i, {}).get("parts") or []
            heard = set((progress.parts.get(i) if progress else None) or [])
            return {
                "kind": "step", "id": i, "label": " ".join(str(step.get("label") or i).split()),
                "detail": brain._clip(step.get("criterion"), 320), "missing_parts": [p["label"] for p in parts if p["id"] not in heard],
                "question": None,
            }
        if k == "data" and i in data and i not in known:
            item = data[i]
            return {
                "kind": "data", "id": i, "label": " ".join(str(item.get("label") or i).split()),
                "detail": brain._clip(item.get("good"), 240), "missing_parts": [],
                "question": ((aids.get("data") or {}).get(i) or {}).get("question"),
            }
        return None

    if kind and ident:
        return build(kind, ident)
    order: list[tuple[str, str]] = []
    if progress and progress.now and progress.now.kind in ("step", "data"):
        order.append((progress.now.kind, progress.now.id))
    order += [("step" if i in steps else "data", i) for i in (progress.missing if progress else [])]
    order += [("data", i) for i in data] + [("step", i) for i in steps]
    return next((found for k, i in order if (found := build(k, i))), None)


def _item_line(item: dict) -> str:
    what = "a step of the playbook" if item["kind"] == "step" else "something the playbook says to find out"
    line = f'{item["label"]} ({what}) — {item["detail"] or "no detail written"}'
    if item["missing_parts"]:
        line += f'. Still missing: {", ".join(item["missing_parts"])} (ask for the first one)'
    return line


# ---------- checks on what the model wrote ----------


def short(text: Any) -> tuple[str, bool]:
    """(the line as it appears on its own, whether it was cut): whole sentences while they fit in ANSWER_MAX_WORDS, at most
    ANSWER_MAX_SENTENCES; a first sentence too long on its own is cut at its last pause inside the limit."""
    line = " ".join(str(text or "").split())
    if not line:
        return "", False
    sentences = re.split(r"(?<=[.?!…])\s+", line)
    kept: list[str] = []
    for sentence in sentences[:ANSWER_MAX_SENTENCES]:
        if len(" ".join(kept + [sentence]).split()) > ANSWER_MAX_WORDS:
            break
        kept.append(sentence)
    if kept:
        out = " ".join(kept)
        return out, out != line
    head = " ".join(sentences[0].split()[:ANSWER_MAX_WORDS])
    pause = max(head.rfind(","), head.rfind(";"), head.rfind(":"))
    if pause > 0 and len(head[:pause].split()) >= ANSWER_MAX_WORDS // 3:
        head = head[:pause]
    return head.rstrip(" ,;:") + "…", True


def offset_in(quote: str, text: str) -> int:
    """Where a quote starts inside a turn: its longest opening that is in the turn's words (a quote may drop a word they said)."""
    words = brain.normalize(re.split(r"…|\.\.\.", quote)[0]).split()
    plain = f" {brain.normalize(text)} "
    for size in range(len(words), 0, -1):
        at = plain.find(f" {' '.join(words[:size])} ")
        if at >= 0:
            return at
    return 0


def said_position(turn_ids: list[str], title: str, req: LiveReading) -> tuple[int, int]:
    """Where a point was said: its first turn in the call, then where its words start inside that turn."""
    turn = next(n for n, t in enumerate(req.turns) if t.id == turn_ids[0])
    return turn, offset_in(title, req.turns[turn].text)


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
    deepen = deepen_on(req, ctx)
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
        if type_key == "deepen" and not deepen:
            drop("deepen_off")
            continue
        if source in custom and type_key not in ("question", "deepen"):
            type_key = source  # it followed the team's own objection: that is what it is
        if type_key not in ("question", "deepen") and type_key not in FIXED_TYPES and type_key not in custom:
            type_key = "other"
        kind = type_key if type_key in ("question", "deepen") else "objection"
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
        if kind == "deepen":
            blocked = _deepen_blocked(item, source, turn_ids, req, by_id, sources, points)
            if blocked:
                drop(blocked)
                continue
            item = {**item, "grounded": True, "decision": None}  # an opportunity from a step: never a fact, never a decision
        content = _content(item, snapshot, sources, allowed, drop)
        if not content.get("say_text"):
            drop("empty_say")
            continue
        if kind == "deepen":
            if any(_similar_deepen(quote, content["say_text"], p.title, p.say or "") for p in req.points if p.kind == "deepen"):
                drop("deepen_same_topic")
                continue
            content.update(_deepen_source(source, snapshot))
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
        content["_at"] = said_position(turn_ids, quote, req)
        points.append({
            "id": new_id, "is_update": False, "kind": kind, "tag_key": type_key, "tag": custom.get(type_key),
            "title": quote, "turn_ids": turn_ids, "said_at": by_id[turn_ids[0]].t, "repeated": False, "outcome": "open", **content,
        })

    # The points of one turn come back together, in the order they were said (updates are merged by id: their place does not matter).
    points = [p for p in points if p["is_update"]] + sorted((p for p in points if not p["is_update"]), key=lambda p: p.pop("_at"))

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
    out: dict[str, Any] = {
        "points": points, "closed": closed, "nothing": not points and not closed,
        "guards": guards, "playbook_version_id": ctx.playbook_version_id,
    }
    if req.reason == "responder":
        # Responder with nothing to answer: no new point and no earlier one brought back into view.
        out["next"] = _next(raw, req, ctx, allowed, drop) if not points else None
    return out


# ---------- go deeper ----------


def _sentence_of(quote: str, text: str) -> str:
    """The sentence of a turn that holds the quote (a figure about something else in the same turn does not count); the
    whole turn when the quote is not found in one sentence."""
    for sentence in re.split(r"(?<=[.?!…;])\s+", " ".join(text.split())):
        if brain.quote_in(quote, sentence):
            return sentence
    return text


def _deepen_blocked(
    item: dict, source: str, turn_ids: list[str], req: LiveReading, by_id: dict[str, LiveTurn], sources: dict[str, str], written: list[dict],
) -> Optional[str]:
    """Why a new "go deeper" point must not be shown, or None. The model judges what is important; code holds the rules that
    can be checked: it serves a step of this playbook, one open at a time and never two in a reading, never on a figure already
    given, never while the rep follows it up."""
    if not source.startswith("step:") or source not in sources:
        return "deepen_without_step"
    if any(p.kind == "deepen" and p.outcome == "open" for p in req.points) or any(p.get("kind") == "deepen" and not p["is_update"] for p in written):
        return "deepen_one_open"
    quote = str(item.get("quote") or "")
    turn = by_id[turn_ids[-1]]
    if brain.numbers_in(_sentence_of(quote, turn.text) if quote else turn.text):
        return "deepen_figure_given"
    last = max(i for i, t in enumerate(req.turns) if t.id in turn_ids)
    if any(t.who == "you" and "?" in t.text for t in req.turns[last + 1:]):
        return "deepen_rep_following"
    if not shares_their_words(str(item.get("say") or ""), " ".join(by_id[i].text for i in turn_ids)):
        return "deepen_not_their_words"
    return None


def _stems(text: str) -> set[str]:
    return {w[:5] for w in brain.normalize(text).split() if len(w) >= 4 and w not in _COMMON}


def shares_their_words(question: str, said: str) -> bool:
    """The question to go deeper is built on what they said (spec: "in the prospect's words"): it shares a word with their turn.
    A question that could follow any sentence is the noise this trigger must not make."""
    return bool(_stems(question) & _stems(said))


def _similar_deepen(quote: str, say: str, title: str, shown: str) -> bool:
    return similar(quote, title, DEEPEN_SAME_TOPIC) or (bool(shown) and similar(say, shown, DEEPEN_SAME_TOPIC))


def _deepen_source(source: str, snapshot: Optional[dict]) -> dict[str, Any]:
    """A deepen point is an opportunity, not an answer: no decision, and its source is the step it serves."""
    step_id = source.removeprefix("step:")
    label = next(
        (" ".join(str(s.get("label") or step_id).split()) for s in (snapshot or {}).get("steps") or [] if isinstance(s, dict) and s.get("step_id") == step_id),
        step_id,
    )
    return {"decision": None, "decision_note": None, "source": {"id": step_id, "label": f"Playbook · {label}"}}


# ---------- Responder with nothing: the next best question ----------


def _checked_line(text: Any, allowed: set[str], drop) -> Optional[str]:
    said = " ".join(str(text or "").split())
    if not said:
        return None
    line, cut = short(said)
    if cut:
        drop("answer_cut")
    if brain.invented_numbers(said, allowed):
        drop("invented_number")
        return None
    return line or None


def _next(raw: Optional[dict], req: LiveReading, ctx: brain.BrainContext, allowed: set[str], drop) -> Optional[dict]:
    """The missing item that matters most and its question in the call's words; the playbook's own question for it when the
    model wrote none; None when nothing is pending or there is no question to ask."""
    item = pending_item(req, ctx)
    if item is None:
        return None
    wrote = (raw or {}).get("next")
    question = _checked_line(wrote.get("question") if isinstance(wrote, dict) else None, allowed, drop)
    if question is None and item["question"]:
        question = _checked_line(item["question"], allowed, drop)
    if question is None:
        drop("next_without_question")
        return None
    return {"kind": item["kind"], "id": item["id"], "label": item["label"], "question": question}


def _content(item: dict, snapshot: Optional[dict], sources: dict[str, str], allowed: set[str], drop) -> dict[str, Any]:
    """decision, what to say and its source: the part of a point that is the brain's judgement, after the checks."""
    said = " ".join(str(item.get("say") or "").split())
    say, cut = short(said)
    if cut:
        drop("answer_cut")
    decision = item.get("decision") if item.get("decision") in DECISIONS else None
    if decision and not snapshot:
        decision = None  # no playbook to justify it (rule 2)
        drop("decision_without_playbook")
    note = brain._clip(item.get("why") or item.get("decision_note"), 80) if decision and decision != "responder" else ""
    if say and brain.invented_numbers(said, allowed):
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


# ---------- Responder on a card already shown: the same point from another angle ----------

REWRITE_SYSTEM = """You are Vocify's live assist. On a live sales call the line shown to the rep for something the prospect said did
not help. Write ONE other way to say it, from ANOTHER ANGLE of the SAME SOURCE below. Never a new fact.
- With a SOURCE: everything you claim about the company or the product is written in the SOURCE; take another of its angles (anchor
  on what the prospect told you before giving the figure, ask what must not be touched, another reason the source gives), tied to
  what the prospect said.
- With no SOURCE (the answer is not in the company's knowledge): never a fact, never a yes or no. Write a question back about
  what they need («¿Qué tendría que hacer para que os sirva?»).
- Never presume anything about the prospect or the deal that the CALL does not show: an earlier agreement, a pilot or a trial, a
  success criterion, a change of tool, which CRM they use, their figures. A source's example or guidance is written for any
  prospect: keep only what this call supports, or turn it into a question.
- It must say something different from every version already shown, not the same words rearranged.
- Words the rep says to the prospect, in the prospect's language, at most 15 words, at most two short sentences. No exclamation
  marks, no lists, no placeholders, no filler openings. Never a day of the month; never a number that is not in the SOURCE or the call.
- No honest other angle? "answer" is null.
OUTPUT: only valid JSON: {"answer": string or null}"""


def source_text(source_id: Optional[str], req: LiveReading, ctx: brain.BrainContext) -> Optional[str]:
    """What a point's source says, written out: a playbook entry's guidance, a step, the knowledge, the offer or earlier calls.
    None when this reading does not have that source."""
    snapshot = ctx.snapshot or {}
    if not source_id:
        return None
    for entry in snapshot.get("entries") or []:
        if isinstance(entry, dict) and entry.get("entry_id") == source_id and str(entry.get("guidance") or "").strip():
            name = " ".join(str(entry.get("label") or entry.get("category") or source_id).split())
            said = f' (they say: «{brain._clip(entry.get("trigger"), 160)}»)' if entry.get("trigger") else ""
            return f"Playbook answer «{name}»{said}: {brain._clip(entry.get('guidance'), 1200)}"
    step_id = source_id.removeprefix("step:")
    for step in snapshot.get("steps") or []:
        if isinstance(step, dict) and step.get("step_id") == step_id:
            return f"Playbook step «{brain._clip(step.get('label'), 80)}»: {brain._clip(step.get('criterion'), 400)}"
    if source_id == "knowledge" and ctx.knowledge:
        call_text = "\n".join(t.text for t in req.turns[-30:])
        return brain.format_company_knowledge(ctx.knowledge, call_text=call_text) or None
    if source_id == "offer" and ctx.product_context.strip():
        return f"The rep's offer: {brain._clip(ctx.product_context, 2000)}"
    if source_id == "history" and (ctx.history or "").strip():
        return f"Earlier calls with this contact: {brain._clip(ctx.history, 2000)}"
    if source_id == "call":
        return "What the prospect said in this call (above): nothing about the company."
    return None


def _recent_turns(req: LiveReading, around: Optional[list[str]] = None) -> list[LiveTurn]:
    """The last minutes of the call (and the turns a point came from, when they are older)."""
    if not req.turns:
        return []
    end = req.turns[-1].t
    lo, hi = STEP_WINDOW_TURNS
    start = min(max(0, len(req.turns) - lo), next((i for i, t in enumerate(req.turns) if t.t >= end - STEP_WINDOW_S), len(req.turns)))
    start = max(start, len(req.turns) - hi)
    if around:
        first = next((i for i, t in enumerate(req.turns) if t.id in around), start)
        start = min(start, max(0, first - 2))
    return req.turns[start:]


def build_rewrite_prompt(req: LiveReading, ctx: brain.BrainContext, point: PointIn, source: Optional[str]) -> str:
    shown = [v for v in point.versions if v.strip()] or ([point.say] if point.say else [])
    return (
        f"PREFERRED LANGUAGE HINT: {req.language}\n{ctx.today}\n\n"
        f"CALL, the last minutes (turn ids in brackets):\n{brain.transcript_block(_recent_turns(req, point.turn_ids))}\n\n"
        f"THE POINT: {point.kind} · their words: «{brain._clip(point.title, 200)}» · turns {','.join(point.turn_ids) or '?'}\n"
        f"VERSIONS ALREADY SHOWN:\n" + ("\n".join(f"- {v}" for v in shown) or "- (none)") + "\n\n"
        f"SOURCE: {source or 'none: the answer is not in the company knowledge. Write a question back, never a fact.'}\n\nJSON only."
    )


def finalize_rewrite(raw: Optional[dict], req: LiveReading, ctx: brain.BrainContext, point: PointIn, grounded: bool) -> dict[str, Any]:
    guards: dict[str, int] = {}

    def drop(reason: str) -> None:
        guards[reason] = guards.get(reason, 0) + 1

    version = (req.target.version if req.target else 1) + 1
    answer = _checked_line((raw or {}).get("answer"), brain.allowed_numbers(req, ctx), drop)
    shown = [v for v in point.versions if v.strip()] or ([point.say] if point.say else [])
    if answer and any(similar(answer, v, REWRITE_SAME) or brain.normalize(answer) == brain.normalize(v) for v in shown):
        drop("rewrite_same_as_shown")
        answer = None
    if answer and not grounded and "?" not in answer:
        drop("rewrite_unknown_not_a_question")  # an unknown point gets a question back, never a fact
        answer = None
    return {"rewrite": {"point_id": point.id, "version": version, "answer": answer} if answer else None, "guards": guards}


# ---------- Pasos: a question for one pending item ----------

STEP_SYSTEM = """You are Vocify's live assist. During a live sales call the rep tapped a pending item of their playbook and wants ONE
question to ask now that moves it forward.
- Build it from the last minutes of the CALL, with the prospect's own words; never ask what they already said or what is KNOWN.
- For an item with missing parts, ask for the FIRST missing part.
- Never presume anything the CALL does not show: an earlier agreement, work you did with them or companies like theirs, a pilot,
  a change of tool, which CRM they use, their figures. When the item's detail assumes it, ask a plain question instead.
- One question the rep says out loud, in the prospect's language, at most 15 words. No facts about the company, no number that
  was not said, no placeholders, no filler openings, no exclamation marks.
OUTPUT: only valid JSON: {"question": string}"""


def build_step_prompt(req: LiveReading, ctx: brain.BrainContext, item: dict) -> str:
    snapshot = ctx.snapshot or {}
    progress = req.progress
    labels = brain.labels_of(snapshot)
    known = [labels.get(i, i) for i in (progress.known_data if progress else [])]
    return (
        f"PREFERRED LANGUAGE HINT: {req.language}\n\n"
        f"CALL, the last minutes (turn ids in brackets):\n{brain.transcript_block(_recent_turns(req))}\n\n"
        f"KNOWN ALREADY: {', '.join(known) or 'nothing yet'}\n"
        f"ITEM: {_item_line(item)}\n\nJSON only."
    )


async def _small_reading(system: str, prompt: str, kind: str) -> AsyncIterator[dict[str, Any]]:
    """token events, then {"type": "parsed", "raw", "model", "latency_ms"} or an error."""
    async for event in brain.stream_json(system, prompt, kind=kind):
        if event["type"] in ("token", "error"):
            yield event
            if event["type"] == "error":
                return
        else:
            try:
                raw = extract_json(event["text"])
            except ValueError:
                yield {"type": "error", "message": "the model did not write JSON"}
                return
            yield {"type": "parsed", "raw": raw if isinstance(raw, dict) else None, "model": event["model"], "latency_ms": event["latency_ms"]}


async def read_rewrite(req: LiveReading, ctx: brain.BrainContext, base: dict) -> AsyncIterator[dict[str, Any]]:
    empty = {"type": "result", **base, "points": [], "closed": [], "nothing": True, "playbook_version_id": ctx.playbook_version_id}
    point = next((p for p in req.points if req.target and p.id == req.target.point_id), None)
    if point is None:
        yield {**empty, "rewrite": None, "guards": {"rewrite_unknown_point": 1}}
        return
    source = source_text(point.source_id, req, ctx)
    grounded = source is not None and point.source_id != "call"
    async for event in _small_reading(REWRITE_SYSTEM, build_rewrite_prompt(req, ctx, point, source if grounded else None), "rewrite"):
        if event["type"] != "parsed":
            yield event
            continue
        out = finalize_rewrite(event["raw"], req, ctx, point, grounded)
        yield {**empty, **out, "nothing": out["rewrite"] is None, "model": event["model"], "latency_ms": event["latency_ms"]}


async def read_step_question(req: LiveReading, ctx: brain.BrainContext, base: dict) -> AsyncIterator[dict[str, Any]]:
    empty = {"type": "result", **base, "points": [], "closed": [], "nothing": True, "playbook_version_id": ctx.playbook_version_id}
    target = req.target
    item = pending_item(req, ctx, target.kind, target.id) if target and target.kind and target.id else None
    if item is None:
        yield {**empty, "step_question": None, "guards": {"step_not_pending": 1}}
        return
    guards: dict[str, int] = {}

    def drop(reason: str) -> None:
        guards[reason] = guards.get(reason, 0) + 1

    async for event in _small_reading(STEP_SYSTEM, build_step_prompt(req, ctx, item), "ask_step"):
        if event["type"] != "parsed":
            yield event
            continue
        question = _checked_line((event["raw"] or {}).get("question"), brain.allowed_numbers(req, ctx), drop)
        if question is None and item["question"]:
            drop("step_question_from_playbook")
            question = _checked_line(item["question"], brain.allowed_numbers(req, ctx), drop)
        found = {"kind": item["kind"], "id": item["id"], "question": question} if question else None
        yield {**empty, "step_question": found, "nothing": found is None, "guards": guards, "model": event["model"], "latency_ms": event["latency_ms"]}


async def read_points(req: LiveReading, ctx: brain.BrainContext) -> AsyncIterator[dict[str, Any]]:
    """token events while the model writes, then one result event (see the shape in shared/live-call/state.js)."""
    cursor = brain.cursor_of(req.turns)
    base = {"producer": "points", "state_version": req.state_version, "cursor": cursor}
    if not req.turns:
        yield {"type": "result", **base, "points": [], "closed": [], "nothing": True, "skipped": "empty", "guards": {}}
        return
    if req.reason == "rewrite":
        async for event in read_rewrite(req, ctx, {**base, "reason": "rewrite"}):
            yield event
        return
    if req.reason == "ask_step":
        async for event in read_step_question(req, ctx, {**base, "reason": "ask_step"}):
            yield event
        return
    if req.reason not in ASKED and req.cursor and req.cursor == cursor:
        yield {"type": "result", **base, "points": [], "closed": [], "nothing": True, "skipped": "no_new_words", "guards": {}}
        return
    by_id = brain.turns_by_id(req.turns)
    item = pending_item(req, ctx) if req.reason == "responder" else None
    prompt = build_prompt(req, ctx, by_id, item)
    system = SYSTEM_SAY if deepen_on(req, ctx) else SYSTEM
    async for event in brain.stream_json(system, prompt, kind="points"):
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
