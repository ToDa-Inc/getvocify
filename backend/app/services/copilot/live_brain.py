"""What the live call assistant's two producers share: the brain's principle and rules, how a call and a playbook
are shown to the model, the model call (the production path of live help), and the checks that run in code
(identity of turns, verbatim quotes, who spoke). Judgement stays in the model; anything that can be checked is checked.

Spec: docs/superpowers/specs/2026-10-16-live-call-assistant-design.md, "The brain's principle" and "Backend: one brain".
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator, Iterable, Optional

import httpx

from app.config import settings
from app.services.copilot.live_models import LiveTurn
from app.services.copilot.prompts import _approved_answers, _clip, format_company_knowledge
from app.services.copilot.suggest import OPENROUTER_URL, _sse_pieces, first_writer, live_direct, live_provider, live_reasoning
from app.services.llm.shared import extract_json
from app.services.playbooks.motion import GOAL_FOR_MOTION

logger = logging.getLogger(__name__)

PROMPT_VERSION = "live_brain_v1"

# D4's goals in words. A call type without a goal has none: its decisions are limited to answering.
GOAL_TEXT = {
    "meeting_booked": "a meeting booked with the prospect, with a day and a time agreed",
    "demo_booked": "a demo booked with the prospect, with a day and a time agreed",
    "proposal_and_close": "the proposal delivered and a next step agreed with a date",
    "close_date": "a closing date agreed",
}

# The ids a point may name as its source besides the playbook's entries.
GENERIC_SOURCES = {
    "knowledge": "Company knowledge",
    "offer": "The rep's offer",
    "history": "Earlier calls with this contact",
    "call": "What the prospect said",
}

PRINCIPLE = """THE BRAIN'S PRINCIPLE
Everything you decide answers one question: what does this rep need to do RIGHT NOW to get closer to the goal of this call?
You take commercial decisions in context. You do not ask "what did they say and what do I answer?", and you never give
generic sales advice. Example: «We use Salesforce and don't want to change» in a discovery call where the pain is not
found yet: do not compare features; ask which process is hardest with their setup today.

DECISION (per point; the default where the playbook says nothing)
- responder: a direct question whose answer is in the company's knowledge, the offer or the playbook. Give the fact in one sentence.
- reconducir: answering now would not move toward the goal, because a step or a piece of information is still missing first
  (see CALL STATE, "missing"). Do not argue or compare: say the question that finds out what is missing.
- aplazar: not needed for this call's goal, or someone else must confirm it. Say how to note it and move on honestly.
- cerrar: the goal is within reach (they agree, they ask how to go on). Say the concrete next step: a day, never an hour you were not given.

RULES (all of them, always)
1. The company's playbook wins. Where an approved answer's guidance says what to do, do that, even when it differs from the
   table above (a playbook that says to give the price honestly means price is never "aplazar" for this company). Keep its idea and its claims.
2. A decision comes from the CALL STATE (what is missing) and the PLAYBOOK, never from generic sales advice. With no state or
   playbook to justify it, decision is null and you only answer.
3. A direct question is never dodged: the fact in one sentence first when it exists, then the question that redirects.
4. Source or silence. Every claim about the company or its product comes from the PLAYBOOK's approved answers, COMPANY
   KNOWLEDGE, the OFFER or EARLIER CALLS; what the prospect said in this call is yours to use. Never invent a customer,
   number, date, feature, integration or promise. If the fact is not written there, you do not have it.
5. Never answer the rep's own words (a "You:" line, an echo of the rep, a wrong speaker label). In doubt, no point.
6. Write in the language the prospect speaks, whatever the language of these instructions.
7. "Probability" is only a way of ranking: never write or compute a probability."""

DATES = """DATES
TODAY is the only date you know. Never write a day of the month or an exact date: name a weekday inside the next two weeks
("el jueves", "mañana") or a month counted from TODAY. Give an hour only when the transcript gave one; to propose two slots
offer two days ("¿el jueves o el viernes?")."""


def goal_for(motion: Optional[str]) -> Optional[str]:
    return GOAL_TEXT.get(GOAL_FOR_MOTION.get(motion or ""))


@dataclass(frozen=True)
class BrainContext:
    """What a reading knows besides the call: read by the endpoint (from the short-lived live-help cache)."""

    snapshot: Optional[dict]
    knowledge: Optional[dict]
    product_context: str
    history: Optional[str]
    today: str
    playbook_version_id: Optional[str] = None


# ---------- how the call and the playbook are shown ----------


def normalize(text: Any) -> str:
    """Lower case, no accents or punctuation, single spaces: for comparing a quote with the words it quotes."""
    import unicodedata

    plain = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", plain.lower()).split())


def turn_line(turn: LiveTurn) -> str:
    who = "Them" if turn.who == "them" else "You"
    name = f" ({turn.name})" if turn.who == "them" and turn.name else ""
    return f"[{turn.id}] {who}{name}: {' '.join(turn.text.split())}"


def transcript_block(turns: list[LiveTurn]) -> str:
    """The call with turn ids. It only grows at its end, so the provider can reuse the prompt up to there."""
    return "\n".join(turn_line(t) for t in turns) or "(empty)"


def window_line(focus_from: Optional[str]) -> str:
    """Where the reading window starts, said after the call so that the call itself stays the same between readings."""
    return f"READING WINDOW: from turn {focus_from} to the end; the turns before it are context." if focus_from else "READING WINDOW: the whole call."


def playbook_header(snapshot: Optional[dict], motion: Optional[str], type_label: Optional[str]) -> str:
    goal = goal_for(motion)
    name = f' "{type_label}"' if type_label else ""
    if not snapshot:
        return f"PLAYBOOK: this call type{name} has no playbook. Use COMPANY KNOWLEDGE and the OFFER only; decision is null.\nGOAL: {goal or 'none known'}"
    return f"PLAYBOOK for this call type{name} (key {motion or '-'}).\nGOAL: {goal or 'the playbook states none: decisions are limited to answering'}"


def entries_block(snapshot: Optional[dict]) -> str:
    lines = _approved_answers(snapshot or {})
    return "APPROVED ANSWERS (id · category \"name\" (they say) : guidance)\n" + ("\n".join(lines) if lines else "(none)")


def steps_block(snapshot: dict) -> str:
    rows = []
    for step in snapshot.get("steps") or []:
        if not isinstance(step, dict) or not step.get("step_id"):
            continue
        example = f' Example: «{_clip(step.get("example"), 240)}»' if step.get("example") else ""
        rows.append(f'- {step["step_id"]} · {_clip(step.get("label"), 80)} — {_clip(step.get("criterion"), 320)}{example}')
    return "STEPS (the rep's ordered playbook; id · label — criterion)\n" + ("\n".join(rows) if rows else "(none)")


def qualification_block(snapshot: dict) -> str:
    rows = [
        f'- {item["criterion_id"]} · {_clip(item.get("label"), 80)} — good answer: {_clip(item.get("good"), 240)}'
        for item in snapshot.get("qualification") or []
        if isinstance(item, dict) and item.get("criterion_id")
    ]
    return "WHAT TO FIND OUT (qualification; id · label — what a good answer is)\n" + ("\n".join(rows) if rows else "(none)")


def labels_of(snapshot: Optional[dict]) -> dict[str, str]:
    """Every id the playbook names (steps, data, entries) with its label."""
    out: dict[str, str] = {}
    for key, id_field in (("steps", "step_id"), ("qualification", "criterion_id"), ("entries", "entry_id")):
        for item in (snapshot or {}).get(key) or []:
            if isinstance(item, dict) and item.get(id_field):
                out[str(item[id_field])] = " ".join(str(item.get("label") or item[id_field]).split())
    return out


def context_blocks(
    *, product_context: Optional[str], knowledge: Optional[dict], history: Optional[str], call_text: str,
) -> str:
    """The parts that stay the same through a call come first (the provider reuses a prompt up to its first change)."""
    offer = (product_context or "").strip() or "(none provided)"
    know = format_company_knowledge(knowledge, call_text=call_text)
    parts = [f"OFFER (what the rep sells, in the rep's words):\n{offer}"]
    if know:
        parts.append(know)
    if (history or "").strip():
        parts.append(
            "EARLIER CALLS WITH THIS CONTACT (anticipate with it, never claim it was said in this call):\n" + history.strip()
        )
    return "\n\n".join(parts)


def allowed_sources(snapshot: Optional[dict], *, has_knowledge: bool, has_offer: bool, has_history: bool) -> dict[str, str]:
    """source id -> label shown on hover. Only what this reading actually has."""
    sources = {"call": GENERIC_SOURCES["call"]}
    if has_knowledge:
        sources["knowledge"] = GENERIC_SOURCES["knowledge"]
    if has_offer:
        sources["offer"] = GENERIC_SOURCES["offer"]
    if has_history:
        sources["history"] = GENERIC_SOURCES["history"]
    for entry in (snapshot or {}).get("entries") or []:
        if isinstance(entry, dict) and entry.get("entry_id") and str(entry.get("guidance") or "").strip():
            label = " ".join(str(entry.get("label") or entry.get("category") or entry["entry_id"]).split())
            sources[str(entry["entry_id"])] = f"Playbook · {label}"
    for step in (snapshot or {}).get("steps") or []:
        if isinstance(step, dict) and step.get("step_id"):
            sources[f"step:{step['step_id']}"] = f"Playbook · {' '.join(str(step.get('label') or step['step_id']).split())}"
    return sources


# ---------- checks that run in code ----------


def turns_by_id(turns: Iterable[LiveTurn]) -> dict[str, LiveTurn]:
    return {turn.id: turn for turn in turns}


def _turn_key(raw: Any, by_id: dict[str, LiveTurn]) -> Optional[str]:
    """The turn a model's reference means: the id as listed, or the bare number of it (3 or "[3]" for "t3"), when that is unambiguous."""
    key = str(raw if raw is not None else "").strip().strip("[]").strip()
    if key in by_id:
        return key
    if key.isdigit():
        tails = [i for i in by_id if i.lstrip("tT-_") == key]
        return tails[0] if len(tails) == 1 else None
    return None


def real_turn_ids(ids: Any, by_id: dict[str, LiveTurn], who: Optional[str] = None) -> list[str]:
    """The ids that are turns of this call (and, when asked, said by `who`), in order, once each."""
    out: list[str] = []
    for item in ids if isinstance(ids, list) else []:
        key = _turn_key(item, by_id)
        if key and key not in out and (who is None or by_id[key].who == who):
            out.append(key)
    return out


def locate_quote(quote: Any, turns: Iterable[LiveTurn], who: Optional[str] = None) -> list[str]:
    """The turns (of this side) whose words contain the quote: when the model quoted right and cited the wrong turn, the
    evidence is still the quote, found where it was said."""
    return [t.id for t in turns if (who is None or t.who == who) and quote_in(quote, t.text)]


def _said_in_order(fragment: list[str], turn: list[str]) -> bool:
    """Every word of the fragment is in the turn, in order and close together: a quote that drops the stutter
    («te te pongo» quoted as «te pongo») is still the words that were said."""
    if len(fragment) < 3:
        return " ".join(fragment) in " ".join(turn)
    for start, word in enumerate(turn):
        if word != fragment[0]:
            continue
        at = 1
        for end in range(start + 1, min(len(turn), start + 2 * len(fragment) + 3)):
            if turn[end] == fragment[at]:
                at += 1
                if at == len(fragment):
                    return True
    return False


def quote_in(quote: Any, text: str) -> bool:
    """The quote's words are in this text (accents, case, punctuation and repeated words aside). «a … b» is two quotes."""
    fragments = [normalize(f).split() for f in re.split(r"…|\.\.\.", str(quote or ""))]
    fragments = [f for f in fragments if f]
    words = normalize(text).split()
    return bool(fragments) and sum(len(f) for f in fragments) >= 2 and all(_said_in_order(f, words) for f in fragments)


def is_quote_of(quote: Any, turn_ids: list[str], by_id: dict[str, LiveTurn]) -> bool:
    """The quote is in one of these turns. Evidence is a quote or nothing."""
    return any(quote_in(quote, by_id[i].text) for i in turn_ids if i in by_id)


def cursor_of(turns: list[LiveTurn]) -> Optional[str]:
    """Identifies the last words of the call: the same cursor means nothing new was said."""
    return f"{turns[-1].id}:{len(turns[-1].text)}" if turns else None


def last_prospect_turn_index(turns: list[LiveTurn], ids: list[str]) -> int:
    positions = [i for i, turn in enumerate(turns) if turn.id in ids]
    return max(positions) if positions else -1


# ---------- the model ----------


def token_budget(kind: str) -> int:
    return {"points": 700, "progress": 1400, "recap": 500, "aids": 2400, "rewrite": 160, "ask_step": 120}[kind]


async def stream_json(system: str, user: str, *, kind: str) -> AsyncIterator[dict[str, Any]]:
    """Yields {"type": "token", "text"} while the model writes, then {"type": "text", "text", "model", "latency_ms"}
    with the whole answer, or {"type": "error", "message"}. The production path of live help: the direct provider
    first, OpenRouter as its backup after COPILOT_HEDGE_MS (see suggest.stream_objection_suggestion)."""
    api_key = (settings.OPENROUTER_API_KEY or "").strip()
    direct = live_direct()
    if not api_key and not direct:
        yield {"type": "error", "message": "no model provider is configured"}
        return
    model = (settings.COPILOT_MODEL or "").strip() or "deepseek/deepseek-v4.1-flash"
    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0.1,
        "stream": True,
        "max_tokens": token_budget(kind),
        "response_format": {"type": "json_object"},
        **live_reasoning(),
        **live_provider(),
    }
    router_headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": settings.FRONTEND_URL,
        "X-Title": "Vocify Live Brain",
    }
    started = time.perf_counter()
    assembled, winner = "", ""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(45.0, connect=10.0)) as client:
            sources = []
            if direct:
                url, key, direct_model = direct
                direct_payload = {
                    **{k: v for k, v in payload.items() if k not in ("reasoning", "provider")},
                    "model": direct_model,
                    "reasoning_effort": live_reasoning()["reasoning"]["effort"],
                }
                sources.append(("direct", lambda: _sse_pieces(client, url, {"Authorization": f"Bearer {key}"}, direct_payload)))
            if api_key:
                sources.append(("openrouter", lambda: _sse_pieces(client, OPENROUTER_URL, router_headers, payload)))
            async for winner, text in first_writer(sources, settings.COPILOT_HEDGE_MS / 1000):
                assembled += text
                yield {"type": "token", "text": text}
        used = f"direct:{direct[2]}" if winner == "direct" and direct else f"openrouter:{model}"
        yield {"type": "text", "text": assembled, "model": used, "latency_ms": int((time.perf_counter() - started) * 1000)}
    except Exception as exc:
        logger.exception("Live brain model call failed")
        yield {"type": "error", "message": str(exc) or type(exc).__name__}


async def complete_json(system: str, user: str, *, kind: str) -> tuple[Optional[dict], dict[str, Any]]:
    """(parsed answer or None, {"model", "latency_ms", "error"}) for a producer that does not stream to the screen."""
    meta: dict[str, Any] = {"model": None, "latency_ms": None, "error": None}
    async for event in stream_json(system, user, kind=kind):
        if event["type"] == "error":
            meta["error"] = event["message"]
        elif event["type"] == "text":
            meta.update(model=event["model"], latency_ms=event["latency_ms"])
            try:
                parsed = extract_json(event["text"])
            except ValueError:
                meta["error"] = "the model did not write JSON"
                return None, meta
            return (parsed if isinstance(parsed, dict) else None), meta
    return None, meta


# ---------- numbers: the one invention that can be checked in code ----------

_DIGITS = re.compile(r"\d+")
_SPOKEN = {
    **{w: str(n) for n, w in enumerate("cero uno dos tres cuatro cinco seis siete ocho nueve diez once doce trece catorce quince".split())},
    **{w: str(n) for n, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen".split())},
    "una": "1", "dieciseis": "16", "diecisiete": "17", "dieciocho": "18", "diecinueve": "19", "veinte": "20", "veintiuno": "21",
    "veintidos": "22", "veintitres": "23", "veinticuatro": "24", "veinticinco": "25", "veintiseis": "26", "veintisiete": "27",
    "veintiocho": "28", "veintinueve": "29", "treinta": "30", "cuarenta": "40", "cincuenta": "50", "sesenta": "60", "setenta": "70",
    "ochenta": "80", "noventa": "90", "cien": "100", "ciento": "100", "mil": "1000", "sixteen": "16", "seventeen": "17",
    "eighteen": "18", "nineteen": "19", "twenty": "20", "thirty": "30", "forty": "40", "fifty": "50", "hundred": "100", "thousand": "1000",
}


def allowed_numbers(req: Any, ctx: "BrainContext") -> set[str]:
    """Every number the reading was given: the offer, knowledge, history, the playbook, today's date and the call so far."""
    parts = [ctx.product_context, ctx.today, ctx.history or "", format_company_knowledge(ctx.knowledge)]
    parts += [dump_snapshot_text(ctx.snapshot)] + [t.text for t in req.turns]
    return set().union(*(numbers_in(part) for part in parts))


def dump_snapshot_text(snapshot: Optional[dict]) -> str:
    """The playbook's words a line may take figures from. A step's `example` is not one: it is another prospect's sentence
    («22 comerciales en España»), and its figures are not this call's."""
    return " ".join(
        str(v) for key in ("steps", "entries", "qualification") for item in (snapshot or {}).get(key) or []
        if isinstance(item, dict) for k, v in item.items() if k != "example" and isinstance(v, (str, int, float))
    )


def numbers_in(text: Any) -> set[str]:
    """The numbers a text says, as digit strings: written as digits or spelled out (uno ... cien, one ... hundred)."""
    plain = normalize(text)
    return set(_DIGITS.findall(plain)) | {_SPOKEN[w] for w in plain.split() if w in _SPOKEN}


def invented_numbers(line: Any, allowed: set[str]) -> list[str]:
    """Numbers in a line the rep would say that no source and nothing said in the call contains: a figure, a count, an hour."""
    return sorted(n for n in _DIGITS.findall(normalize(line)) if n not in allowed)
