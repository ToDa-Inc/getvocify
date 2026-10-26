"""The strategic card of the live call assistant (pilot, company flag LIVE_CARD_ENABLED): ONE intervention, or silence.

A port of the replay engine frozen for the pilot on 2026-10-26 (backend/evals/strategic/run_turns.py, "turns-6b"):
the same prompt, the same small gate and the same screen rule. Only what a live call needs is different: the renderer
sends the call and the cards already shown (the producer stays stateless, like the points producer) and says why it
reads; the code decides whether that is a moment turns-6b would read at.

- One reading: what is happening, their latest words, the last move, then a card or silence (DeepSeek, strict JSON).
- Code checks what can be checked: at most 35 words, a fact cited from the playbook really is there, no number an
  answer invents, not the same text as a card already shown, not after their goodbye.
- The small gate, in parallel: facts (only against the approved text and the conversation), the call closing, and a
  repeat of a move already made (one more try for a different move, or silence).
- The screen holds one card until the rep could use it: they said REP_WORDS words of substance since it appeared, or
  the other side began and finished a new intervention, or the rep closed it. A card that came while they were still
  talking may be replaced at the end of that intervention.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from datetime import date, timedelta
from difflib import SequenceMatcher
from typing import Any, Callable, Optional

import httpx

from app.config import settings
from app.services.copilot import live_brain as brain
from app.services.copilot.suggest import OPENROUTER_URL, live_direct, live_provider, live_reasoning
from app.services.llm.shared import extract_json

logger = logging.getLogger(__name__)

PROMPT_VERSION = "strategic_turns6b"

# ---------- the prompts, word for word as tested (turns-6b) ----------

SYSTEM = """You are the real-time sales copilot of a salesperson ("the rep", "You") in a call with a prospect ("Them").
You know their company's playbook and everything said so far.

Most moments need nothing from you: the rep is talking, listening or already handling it. You show a card only when one
concrete intervention would help the rep move the conversation toward the company's goal, as far as this conversation
allows.

How to decide, in this order (your answer follows the same order):
1. Understand what is really happening ("what_is_happening"). What they say about their own situation is fact;
   examples, hypotheses, irony and mere interest are not. The transcript can be wrong (misheard words, speakers mixed
   up): read it with common sense. "understanding_confidence" is "low" when the words are garbled, the meaning is
   ambiguous or it may be irony.
2. What they just said comes first ("their_latest"): a question, an objection, new information, or a limit (no time,
   not this week, email instead, do not quote me). A question or an objection is answered first, with the company's
   approved answer when there is one. Every card respects their limits.
3. The real purpose of the conversation. The playbook's goal is the direction, not an order: when the purpose changes
   (they are not the buyer, they left the company, they are advising, they are already buying), help with that purpose
   instead of forcing the goal.
4. What has already been done ("last_move"): the last card in THE THREAD or the rep's own move on this, and what they
   answered. A move already made is made: the next card responds to their answer with the next step, never the same
   move again, not even reworded. Do not give up at the first no when the playbook says to try again; after a clear no
   more than once, only a genuinely new angle justifies a card.
5. Decide: a card only when it adds something concrete the rep is not already doing; otherwise "silence".

The card: one sentence the rep can say as is, in the language of the call, at most 20 words, natural and respectful,
built from their words. Respect the playbook's mandatory rules; adapt its tactics and examples to this conversation,
never recite them. Never invent facts about the product or commitments they did not make, never state as done what has
not been done (an invitation sent, an email that arrived), never confirm a detail they did not give.

Notes on the data: a fact about the product, prices, customers or results only when the SOURCES say it ("source": the
entry id as written before " · ", "offer" or "knowledge"; "source_quote": the verbatim text of the SOURCES); otherwise
"source" is "context" and "source_quote" is "". For days use the CALENDAR."""
SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["what_is_happening", "understanding_confidence", "their_latest", "last_move", "decision", "line", "source", "source_quote"],
    "properties": {"what_is_happening": {"type": "string"},
                   "understanding_confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                   "their_latest": {"type": "string"}, "last_move": {"type": "string"},
                   "decision": {"type": "string", "enum": ["card", "silence"]},
                   "line": {"type": "string"}, "source": {"type": "string"}, "source_quote": {"type": "string"}},
}
REPEAT_SYSTEM = """A live assistant wants to show a salesperson ONE new card. The cards already shown in this call are
listed, then what was said since the last one. Is the new card the same move as a card already shown (the same request,
proposal or question, even in other words) while the other side has not answered that card with anything new? A move
adapted to something new they said (a new constraint, a new person, an answer, a new topic) is not a repeat. Answer JSON
{"repeats": true|false, "same_as": "the earlier card it repeats, or empty", "why": "at most 10 words"}."""
REPEAT_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["repeats", "same_as", "why"],
                 "properties": {"repeats": {"type": "boolean"}, "same_as": {"type": "string"}, "why": {"type": "string"}}}
FACT_SYSTEM = """A live assistant wrote ONE line for a salesperson on a call. Check what the line states as true or
commits to. What is inside a question («¿…?») states nothing, even when it names a tool or offers options («¿te va
bien el martes a las 10?», «¿recibe sugerencias o tiene que consultar la herramienta?»), except what the question
takes for granted about the seller's product: offering to show how the product does something («¿te enseño cómo se
rellenan esos campos sin que los toquen?», «¿te enseño cómo quedaría el Excel actualizado solo?») claims it does it,
and that needs the SOURCE like any statement. Offering to show it in general («¿te lo enseño 15 minutos?») claims
nothing. What is outside the question marks is judged as a statement, also when a question follows it («Con Excel no
hay integración que montar: ¿…?»).
Each kind of content has its own source:
- About the seller's company, team, people or product, or about what another product can do (who founded it, who does
  what, a capability, an integration, a figure, a customer, a result, why something is slow, recording the call): only
  the SOURCE (the company's approved text) supports it. The line may say less than the SOURCE or say it in other words;
  related is not enough.
- What the seller commits to is one of three things:
  · a fact or guarantee about the company or the product (it will work from tomorrow, a trial or access, a discount, a
    price, an integration): only the SOURCE supports it;
  · a proposal: a question or a suggestion of a next step («¿te llamo en enero?», «¿lo vemos el martes a las 10?»): it
    states nothing, fine when it fits the conversation;
  · an action under the seller's own control (sending the information or an invitation, calling back, writing): fine
    when the seller can simply do it and it fits what was said («te mando la información hoy» after they asked for it).
    What it adds still needs THE CONVERSATION: a person nobody mentioned («con vuestra directora comercial»), or a date
    stated as already agreed («quedamos en enero») when they did not agree it.
- About the other side (their tools, team, situation, what they said or asked): THE CONVERSATION supports it. Naming a
  tool they said they use is not a claim about that tool.
- Stating as done what the seller has not done («te acaba de llegar la invitación», «ya te lo he mandado») is a
  statement about the conversation: unsupported unless THE CONVERSATION shows it happened. Confirming a detail (a day,
  an hour, a name) that differs from what the other side said («lunes a las 10» when they said «11») contradicts it.
"unsupported" is true when the line states something of the first two kinds that its source does not say, states
something about the other side that THE CONVERSATION contradicts, or contradicts what the seller said. Answer JSON
{"unsupported": true|false, "what": "at most 8 words"}."""
FACT_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["unsupported", "what"],
               "properties": {"unsupported": {"type": "boolean"}, "what": {"type": "string"}}}
CLOSING_SYSTEM = """Is this sales call closing? Closing: the two sides are wrapping up and nothing new is being opened:
goodbyes or farewell wishes, thanking and leaving, confirming the last step and ending. Either side closing
unequivocally is enough, even before the other answers: the other side says goodbye, or the salesperson closes («pues
te deseo mucha suerte», «que vaya muy bien, un abrazo»), unless the other side then reopens with something new. Not
closing: agreeing a next step while the conversation goes on, a thank-you in the middle of the call, a
goodbye one of them takes back («espera, una cosa más»). Answer JSON {"closing": true|false, "evidence": "the words that
show it, copied verbatim from ONE of the last turns; empty when not closing"}."""
CLOSING_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["closing", "evidence"],
                  "properties": {"closing": {"type": "boolean"}, "evidence": {"type": "string"}}}
ACK = {
    "mhm", "mm", "mmm", "hmm", "hm", "ajá", "aja", "ah", "eh", "oh", "uh", "uh-huh", "ok", "okay", "vale", "sí", "si",
    "claro", "total", "exacto", "exactamente", "eso", "es", "correcto", "efectivamente", "cierto", "verdad", "ya", "bien",
    "perfecto", "genial", "entiendo", "entendido", "vaya", "ostras", "guay", "venga", "bueno", "pues", "y", "que",
    "tanto", "obvio", "seguro", "yeah", "yes", "right", "sure",
}

# ---------- the numbers turns-6b was tested with ----------

SECONDS_PER_WORD = 0.33  # a turn ends at the next one's start, or its own start plus its words
MIN_SUBSTANCE = 4  # an intervention with fewer words of substance («sí, claro, dime») is not read
MID_GAP_S = 40.0  # a long intervention is also read every this long while it goes on
REP_FLOOR_S = 45.0  # the rep holding the floor this long is a moment to read
REP_WORDS = 15  # the rep has had the chance to use the card on screen once they said this many words of substance
MIN_SHOW_S = 6.0  # a card on screen is not replaced before this, and never once the rep has started to speak
TOKENS = 450
# The reading is asked for at most 20 words; only a clearly excessive card is refused (half the cards cut at 25 words
# were good ones of 26 to 31 words).
MAX_CARD_WORDS = 35
SOURCE_QUOTE_WORDS, SAME_TEXT = 6, 0.7
FACT_TURNS, FACT_CHARS = 400, 12000
CLOSING_TURNS, CLOSING_RECENT_S = 8, 30.0
THREAD_CARDS, THREAD_WORDS = 3, 45
GOODBYES = ("hasta luego", "hasta mañana", "hasta pronto", "hasta otra", "adiós", "adios", "chao", "chau", "un saludo",
            "bye", "goodbye")
GOODBYE_TAIL_WORDS, AFTER_GOODBYE_SUBSTANCE = 8, 4
BACKCHANNEL_MAX_WORDS, SIGNAL_MAX_WORDS, SIGNAL_MAX_SUBSTANCE = 5, 6, 3
TITLE_WORDS = 14
SOURCE_BLOCKS = ("OFFER (", "COMPANY KNOWLEDGE (", "EARLIER CALLS", "APPROVED ANSWERS", "STEPS (", "WHAT TO FIND OUT")
LINE_BLOCKS = ("APPROVED ANSWERS", "STEPS (", "WHAT TO FIND OUT")  # one entry per line: a quote points at its line
DAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
# The model turns-6b was tested with, on the direct provider; production's live help uses an older snapshot.
CARD_MODEL = "deepseek-ai/DeepSeek-V4.1-Flash-1017"
# Without an answer from the direct provider in this long, the backup starts too (Together stalls for 10-30 s at times).
HEDGE_S = 3.0
TIMEOUT_S = 20.0


# ---------- who holds the floor ----------


def words(text: str) -> int:
    return len(text.split())


def ends(turns: list[dict]) -> list[float]:
    """When each turn finished: the next turn's start, or its own start plus its words."""
    out = []
    for i, t in enumerate(turns):
        own = t["t"] + max(0.45, words(t["text"]) * SECONDS_PER_WORD)
        out.append(max(own, turns[i + 1]["t"]) if i + 1 < len(turns) else own)
    return out


def finished_by(end: list[float], at: float) -> int:
    return sum(1 for e in end if e <= at + 1e-6)


def tokens(text: str) -> list[str]:
    return [w for w in re.split(r"[\s,.;:¿?¡!…\-]+", text.lower()) if w]


def backchannel(text: str) -> bool:
    ws = tokens(text)
    return 0 < len(ws) <= BACKCHANNEL_MAX_WORDS and all(w in ACK for w in ws)


def substance(text: str) -> int:
    """Words that are not acknowledgement: what makes a reply a reply."""
    return sum(1 for w in tokens(text) if w not in ACK)


def signal_like(text: str) -> bool:
    """A backchannel, or a fragment too short to take the floor. A question never is."""
    if "?" in text:
        return False
    return backchannel(text) or (len(tokens(text)) <= SIGNAL_MAX_WORDS and substance(text) <= SIGNAL_MAX_SUBSTANCE)


def listening(turns: list[dict]) -> set[int]:
    """Indexes of turns that are a listening signal said while the other side holds the floor («claro», «dime»)."""
    out = set()
    for i, t in enumerate(turns):
        if not signal_like(t["text"]):
            continue
        before = next((u for u in reversed(turns[:i]) if not signal_like(u["text"])), None)
        after = next((u for u in turns[i + 1:] if not signal_like(u["text"])), None)
        right_after = turns[i + 1] if i + 1 < len(turns) else None
        if before and before["who"] != t["who"] and (after is None or after["who"] != t["who"]
                                                     or (right_after is not None and right_after["who"] != t["who"])):
            out.add(i)
    return out


def floors(turns: list[dict]) -> list[dict]:
    """Stretches where one side holds the floor: {who, first, last}, the other side's listening signals inside."""
    signals = listening(turns)
    out: list[dict] = []
    for i, t in enumerate(turns):
        if i in signals:
            continue
        if out and out[-1]["who"] == t["who"]:
            out[-1]["last"] = i
        else:
            out.append({"who": t["who"], "first": i, "last": i})
    return out


def own_turns(turns: list[dict], floor: dict, signals: set[int]) -> list[int]:
    return [i for i in range(floor["first"], floor["last"] + 1) if i not in signals and turns[i]["who"] == floor["who"]]


def them_floors(turns: list[dict], end: list[float]) -> list[tuple[float, float]]:
    """(start, end) of each intervention of the other side."""
    signals = listening(turns)
    return [(turns[f["first"]]["t"], end[max(own_turns(turns, f, signals))]) for f in floors(turns) if f["who"] == "them"]


def rep_said(turns: list[dict], after: float, until: float) -> int:
    """Words of substance the rep said between two moments; listening signals do not count."""
    signals = listening(turns)
    total = 0
    for i, u in enumerate(turns):
        if u["who"] != "you" or i in signals or u["t"] < after or u["t"] > until:
            continue
        spoken = u["text"].split()[: max(0, int((until - u["t"]) / SECONDS_PER_WORD))]
        total += substance(" ".join(spoken))
    return total


# ---------- when it reads ----------


def due(reason: str, objection: Optional[str], turns: list[dict], end: list[float], now: float,
        last_read_t: Optional[float]) -> Optional[str]:
    """The renderer's checkpoint as a turns-6b moment, or None when turns-6b would not read now.
    - turn_end (their pause with a complete idea): "them_urgent" when the turn check saw a question or an objection,
      else "them_end"; only with MIN_SUBSTANCE words of substance said in their intervention since the last reading.
    - long_turn (a breath in a long intervention): "them_mid" every MID_GAP_S seconds of it.
    - rep_turn: "rep_long" once the rep has held the floor REP_FLOOR_S, once per floor."""
    signals = listening(turns)
    held = floors(turns)
    last = last_read_t if last_read_t is not None else -1.0
    if reason in ("turn_end", "long_turn"):
        floor = next((f for f in reversed(held) if f["who"] == "them"), None)
        if floor is None:
            return None
        mine = own_turns(turns, floor, signals)
        if reason == "turn_end":
            if sum(substance(turns[i]["text"]) for i in mine if end[i] > last) < MIN_SUBSTANCE:
                return None
            return "them_urgent" if objection and objection != "none" else "them_end"
        since = max(last, turns[mine[0]]["t"])
        said = sum(substance(turns[i]["text"]) for i in mine if end[i] > since)
        return "them_mid" if now - since >= MID_GAP_S and said >= MIN_SUBSTANCE * 2 else None
    if reason == "rep_turn":
        if not held or held[-1]["who"] != "you":
            return None
        start = turns[own_turns(turns, held[-1], signals)[0]]["t"]
        return "rep_long" if now - start >= REP_FLOOR_S and last < start + REP_FLOOR_S else None
    return None


# ---------- what the reading reads ----------


def sources_text(ctx: Any, motion: Optional[str]) -> str:
    """The SOURCES block: the playbook's goal as a starting point, the offer and the knowledge, the approved answers,
    the steps, what to find out and today's date (the same text the replays read)."""
    header = brain.playbook_header(ctx.snapshot, motion, None).replace(
        "GOAL:", "USUAL GOAL FOR THIS TYPE OF CALL (a starting point, not an obligation):", 1)
    return header + "\n\n" + "\n\n".join([
        brain.context_blocks(product_context=ctx.product_context, knowledge=ctx.knowledge, history=ctx.history, call_text=""),
        brain.entries_block(ctx.snapshot) if ctx.snapshot else "",
        brain.steps_block(ctx.snapshot) if ctx.snapshot else "",
        brain.qualification_block(ctx.snapshot) if ctx.snapshot else "",
        ctx.today,
    ])


def calendar(sources: str, days: int = 28) -> str:
    """The next weeks with their weekdays, written by the code (a reading called 11 November a Tuesday)."""
    m = re.search(r"TODAY: \w+ (\d{4})-(\d{2})-(\d{2})", sources)
    if not m:
        return ""
    today = date(int(m[1]), int(m[2]), int(m[3]))
    return "CALENDAR: " + ", ".join(f"{DAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]}" + (" (hoy)" if d == today else "")
                                    for d in (today + timedelta(k) for k in range(days)))


def log_text(turns: list[dict], end: list[float], shown: list[dict]) -> str:
    """The conversation with each card the rep saw after the turn it appeared at."""
    screen: dict[int, list[str]] = {}
    for s in sorted(shown, key=lambda s: s["visible_t"]):
        screen.setdefault(finished_by(end, s["visible_t"]) - 1, []).append(s["say"])
    lines = []
    for i, t in enumerate(turns):
        lines.append(f"[{t['id']}] {'Them' if t['who'] == 'them' else 'You'}: {' '.join(t['text'].split())}")
        lines += [f"    [card shown] «{say}»" for say in screen.get(i, [])]
    return "\n".join(lines) or "(nothing said yet)"


def thread(turns: list[dict], end: list[float], shown: list[dict], now: float) -> str:
    """The latest cards and what each side said after each one: the moves already made and their answers."""
    out = []
    recent = [s for s in shown if s["visible_t"] <= now][-THREAD_CARDS:]
    for k, s in enumerate(recent):
        until = recent[k + 1]["visible_t"] if k + 1 < len(recent) else now
        said: dict[str, list[str]] = {"you": [], "them": []}
        for i, t in enumerate(turns):
            if s["visible_t"] < end[i] and t["t"] <= until:
                said[t["who"]] += t["text"].split()
        them = " ".join(said["them"][-THREAD_WORDS:]) or "(nothing yet)"
        you = " ".join(said["you"][-THREAD_WORDS:]) or "(nothing yet)"
        out.append(f"- {int(s['visible_t'] // 60)}:{int(s['visible_t'] % 60):02d} card «{s['say']}»\n    then the rep: {you}\n    then they: {them}")
    return "THE THREAD (the latest moves already made and what came after each):\n" + ("\n".join(out) or "(no card yet)")


def reading_input(sources: str, turns: list[dict], end: list[float], now: float, shown: list[dict]) -> str:
    # The renderer sends what has been said; nobody is mid-word in a transcript that has arrived.
    return (f"{sources}\n\n{calendar(sources)}\n\nLOG (\"You\" is the rep; [card shown] is a card the rep saw):\n"
            f"{log_text(turns, end, shown)}\n\nSPEAKING NOW:\n(nobody)\n\n{thread(turns, end, shown, now)}\n\nNOW: {round(now)} s into the call.")


def conversation_lines(turns: list[dict], end: list[float], now: float, n: int = 12, since: Optional[float] = None,
                       chars: int = 3000) -> str:
    """The latest turns as the checks read them: who said what, the seller's words included."""
    lines = []
    for i, t in enumerate(turns):
        if t["t"] > now:
            break
        if since is not None and end[i] <= since:
            continue
        lines.append(f"{'Seller' if t['who'] == 'you' else 'Other side'}: {' '.join(t['text'].split())}")
    return "\n".join(lines[-n:])[-chars:]


# ---------- checks in code ----------


def source_blocks(sources: str) -> dict[str, str]:
    starts = sorted((sources.find(h), h) for h in SOURCE_BLOCKS if h in sources)
    return {h: sources[i:(starts[k + 1][0] if k + 1 < len(starts) else len(sources))].strip() for k, (i, h) in enumerate(starts)}


def entry_line(sources: str, source: str) -> str:
    """The whole SOURCES line of a playbook entry or step by its id, or "" when there is none."""
    source = source.strip()
    if not source or source in ("context", "knowledge", "offer"):
        return ""
    for line in sources.splitlines():
        if line.strip().startswith(f"- {source} ·") or line.strip().startswith(f"{source} ·"):
            return line.strip().removeprefix("- ")
    return ""


def authorized_text(sources: str, card: dict) -> str:
    """The whole approved source a card rests on: its entry or step, the offer or the knowledge, and the entry or block
    where its quote is found. Facts are checked against this, not against the fragment the model copied."""
    blocks = source_blocks(sources)
    source = (card.get("source") or "").strip()
    quote = " ".join((card.get("source_quote") or "").split())
    parts = [blocks.get("OFFER (", "") if source == "offer" else blocks.get("COMPANY KNOWLEDGE (", "") if source == "knowledge"
             else entry_line(sources, source)]
    if len(quote.split()) >= SOURCE_QUOTE_WORDS:
        for header, block in blocks.items():
            if header in LINE_BLOCKS:
                parts += [line.strip().removeprefix("- ") for line in block.splitlines() if brain.quote_in(quote, line)]
            elif brain.quote_in(quote, block):
                parts.append(block)
    return "\n".join(dict.fromkeys(part for part in parts if part))


def asserted(line: str) -> str:
    """The line without its questions: what it states."""
    line = re.sub(r"¿[^?]*\?", " ", line)
    return re.sub(r"[^.!]*\?", " ", line)


def offered(line: str) -> str:
    """What the line's questions offer to show about the product («¿te enseño cómo se rellenan solos?»): a claim."""
    found = re.findall(r"(?:enseñ|muestr|explic)\w*[^?¿]*?\b(c[oó]mo\s[^?]+)", " ".join(re.findall(r"¿([^?]*)\?", line)))
    return " / ".join(f.strip() for f in found)


def basic_checks(card: dict, turns: list[dict], shown: list[dict], sources: str) -> Optional[str]:
    if not card["say"].strip():
        return "no_evidence"
    if len(card["say"].split()) > MAX_CARD_WORDS:
        return "too_long"
    quote = " ".join((card.get("source_quote") or "").split())
    card["authorized"] = authorized_text(sources, card)
    if (card["act"] == "answer" or quote) and not card["authorized"]:
        return "source_not_found"
    # A number an answer states that neither the call nor its approved source has; a number inside a question proposes.
    said = " ".join(t["text"] for t in turns) + " " + card["authorized"]
    if card["act"] == "answer" and brain.numbers_in(asserted(card["say"])) - brain.numbers_in(said):
        return "invented_number"
    text = f"«{card['say']}»".lower()
    if any(SequenceMatcher(None, text, f"«{s['say']}»".lower()).ratio() > SAME_TEXT for s in shown):
        return "same_text_as_shown"
    return None


def closing_confirmed(result: Optional[dict], turns: list[dict], end: list[float], now: float) -> bool:
    """The check says the call is closing and its evidence was really said in the last CLOSING_RECENT_S seconds."""
    if not result or not result.get("closing"):
        return False
    said = [t["text"] for i, t in enumerate(turns) if t["t"] <= now and end[i] > now - CLOSING_RECENT_S]
    pieces = [" ".join(p.split()) for p in re.split(r"\.\.\.|…", result.get("evidence") or "")]
    pieces = [p for p in pieces if p]
    return bool(pieces) and all(any(brain.quote_in(p, x) for x in said) for p in pieces)


def after_goodbye(turns: list[dict], end: list[float], at: float) -> bool:
    """The other side said goodbye (a turn that ends with it) and has said nothing of substance since."""
    bye = None
    for i, t in enumerate(turns):
        if t["t"] > at:
            break
        tail = " ".join(t["text"].lower().split()[-GOODBYE_TAIL_WORDS:])
        if t["who"] == "them" and end[i] <= at and any(g in tail for g in GOODBYES):
            bye = i
    if bye is None:
        return False
    return not any(t["who"] == "them" and t["t"] <= at and substance(t["text"]) >= AFTER_GOODBYE_SUBSTANCE for t in turns[bye + 1:])


def rep_could_use(shown: list[dict], turns: list[dict], floors_them: list[tuple[float, float]], at: float) -> bool:
    """The rep has had the chance to use the card on screen: they closed it, said REP_WORDS words of substance since it
    appeared, or the other side began and finished a new intervention after it."""
    if not shown or not shown[-1].get("open", True):
        return True
    last = shown[-1]["visible_t"]
    return rep_said(turns, last, at) >= REP_WORDS or any(last < a and b <= at for a, b in floors_them)


def can_update(shown: list[dict], turns: list[dict], floors_them: list[tuple[float, float]], moment: str, at: float) -> bool:
    """The card on screen may be replaced only when it came during the intervention that just ended, the rep has not
    started to speak since, and it has been up MIN_SHOW_S: what they added after it changed the move."""
    if not shown or moment not in ("them_end", "them_urgent"):
        return False
    last = shown[-1]["visible_t"]
    during = any(a <= last <= b + 0.5 and b <= at for a, b in floors_them)
    return during and at - last >= MIN_SHOW_S and rep_said(turns, last, at) < 3


# ---------- the model ----------


async def _post(client: httpx.AsyncClient, url: str, headers: dict, payload: dict) -> str:
    resp = await client.post(url, headers=headers, json=payload)
    if resp.status_code >= 400:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
    content = ((resp.json().get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    if not content.strip():
        raise RuntimeError("empty answer")
    return content


async def ask(system: str, user: str, schema: dict, *, max_tokens: int, temperature: float) -> tuple[Optional[dict], dict]:
    """(parsed JSON or None, {"model", "latency_ms", "error"}): the direct provider with the tested model and a strict
    schema; OpenRouter as its backup, started after HEDGE_S without an answer or as soon as the direct one fails."""
    meta: dict[str, Any] = {"model": None, "latency_ms": None, "error": None}
    effort = live_reasoning()["reasoning"]["effort"]
    base = {
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": temperature, "max_tokens": max_tokens,
        "response_format": {"type": "json_schema", "json_schema": {"name": "reading", "strict": True, "schema": schema}},
    }
    started = time.perf_counter()
    async with httpx.AsyncClient(timeout=httpx.Timeout(TIMEOUT_S, connect=5.0)) as client:
        sources: list[tuple[str, Callable[[], Any]]] = []
        direct = live_direct()
        if direct:
            url, key, _ = direct
            sources.append((f"direct:{CARD_MODEL}", lambda: _post(client, url, {"Authorization": f"Bearer {key}"},
                                                                 {**base, "model": CARD_MODEL, "reasoning_effort": effort})))
        router_key = (settings.OPENROUTER_API_KEY or "").strip()
        if router_key:
            model_r = (settings.COPILOT_MODEL or "").strip() or "deepseek/deepseek-v4.1-flash"
            headers = {"Authorization": f"Bearer {router_key}", "HTTP-Referer": settings.FRONTEND_URL, "X-Title": "Vocify Live Card"}
            sources.append((f"openrouter:{model_r}", lambda: _post(client, OPENROUTER_URL, headers,
                                                                  {**base, "model": model_r, "reasoning": {"effort": effort}, **live_provider()})))
        if not sources:
            meta["error"] = "no model provider is configured"
            return None, meta
        running: dict[asyncio.Task, str] = {}
        errors: list[str] = []

        def start_next() -> None:
            name, call = sources.pop(0)
            running[asyncio.ensure_future(call())] = name

        start_next()
        try:
            while running:
                done, _ = await asyncio.wait(running, timeout=HEDGE_S if sources else None, return_when=asyncio.FIRST_COMPLETED)
                if not done:
                    start_next()
                    continue
                for task in done:
                    name = running.pop(task)
                    try:
                        content = task.result()
                    except Exception as exc:
                        errors.append(f"{name}: {exc}")
                        continue
                    try:
                        parsed = json.loads(content)
                    except json.JSONDecodeError:
                        try:
                            parsed = extract_json(content)
                        except ValueError:
                            errors.append(f"{name}: not JSON")
                            continue
                    meta.update(model=name, latency_ms=int((time.perf_counter() - started) * 1000))
                    return (parsed if isinstance(parsed, dict) else None), meta
                if sources and not running:
                    start_next()
        finally:
            for task in running:
                task.cancel()
    meta.update(error="; ".join(errors) or "no answer", latency_ms=int((time.perf_counter() - started) * 1000))
    return None, meta


async def fact_check(card: dict, conversation: str) -> tuple[Optional[dict], dict]:
    """A line states nothing its approved source or the conversation does not say."""
    source = card.get("authorized") or card.get("source_quote") or "(none: this line has no approved source)"
    stated = " ".join(asserted(card["say"]).split()).strip(" .:;,")
    user = (f"SOURCE: «{source}»\nTHE CONVERSATION (latest last):\n{conversation or '-'}\nTHE LINE: «{card['say']}»\n"
            f"WHAT THE LINE STATES OUTSIDE ITS QUESTIONS: «{stated or '(nothing: only questions)'}»"
            + (f"\nWHAT ITS QUESTIONS OFFER TO SHOW THE PRODUCT DOING (a claim, judged like a statement): «{offered(card['say'])}»"
               if offered(card["say"]) else ""))
    return await ask(FACT_SYSTEM, user, FACT_SCHEMA, max_tokens=700, temperature=0.0)


async def closing_check(conversation: str) -> tuple[Optional[dict], dict]:
    return await ask(CLOSING_SYSTEM, f"THE LAST TURNS (latest last):\n{conversation or '-'}", CLOSING_SCHEMA, max_tokens=80, temperature=0.0)


async def repeat_check(say: str, shown: list[dict], turns: list[dict], end: list[float], at: float) -> tuple[Optional[dict], dict]:
    cards = "\n".join(f"- {int(s['visible_t'] // 60)}:{int(s['visible_t'] % 60):02d} «{s['say']}»" for s in shown)
    since = conversation_lines(turns, end, at, since=shown[-1]["visible_t"]) if shown else ""
    user = f"CARDS ALREADY SHOWN:\n{cards}\nSAID SINCE THE LAST CARD:\n{since or '(nothing)'}\nTHE NEW CARD: «{say}»"
    return await ask(REPEAT_SYSTEM, user, REPEAT_SCHEMA, max_tokens=120, temperature=0.0)


async def _nothing() -> tuple[Optional[dict], dict]:
    return {"repeats": False, "same_as": "", "why": ""}, {"model": None, "latency_ms": 0, "error": None}


# ---------- one reading ----------


async def vet(out: dict, turns: list[dict], end: list[float], now: float, shown: list[dict], sources: str) -> tuple[dict, Optional[str], dict]:
    """The card the reading wrote, through the protections: (card, why it is dropped or None, what each check said)."""
    source = (out.get("source") or "").strip() or "context"
    quote = "" if source == "context" else (out.get("source_quote") or "")  # a line resting on the conversation quotes nothing
    card = {"act": "answer" if source != "context" else "move", "say": (out.get("line") or "").strip(), "source": source,
            "source_quote": quote}
    if card["act"] == "answer" and not authorized_text(sources, card):
        card["act"] = "move"
    why = basic_checks(card, turns, shown, sources)
    if why:
        return card, why, {}
    facts, closing, repeat = await asyncio.gather(
        fact_check(card, conversation_lines(turns, end, now, n=FACT_TURNS, chars=FACT_CHARS)),
        closing_check(conversation_lines(turns, end, now, n=CLOSING_TURNS)),
        repeat_check(card["say"], shown, turns, end, now) if shown else _nothing(),
    )
    checks = {"facts": facts[0], "closing": closing[0], "repeat": repeat[0],
              "check_ms": max(m.get("latency_ms") or 0 for _, m in (facts, closing, repeat))}
    if (facts[0] or {"unsupported": True})["unsupported"]:  # a check that did not answer lets nothing through
        return card, "unsupported_fact", checks
    if closing_confirmed(closing[0], turns, end, now):
        return card, "call_closing", checks
    if after_goodbye(turns, end, now):
        return card, "after_goodbye", checks
    if (repeat[0] or {}).get("repeats"):
        card["same_as"] = repeat[0].get("same_as", "")
        return card, "repeats", checks
    return card, None, checks


def _card_point(card: dict, call_id: str, turns: list[dict], now: float, labels: dict[str, str]) -> dict:
    """The card as a point of the shared state (shared/live-call/state.js): an approved answer is a "Respuesta", any
    other move a "Puedes preguntar" (kind deepen)."""
    them = [t for t in turns if t["who"] == "them"]
    # The island shows their words on the card's first line and drops a point without any: before they have spoken, the
    # latest words said.
    said = them[-1] if them else turns[-1]
    source = card["source"] if card["act"] == "answer" else None
    label = (labels.get(source) or labels.get(f"step:{source}")) if source else None
    entry = bool(source and source not in ("offer", "knowledge") and label)
    return {
        "id": "card-" + hashlib.sha1(f"{call_id}|{now:.1f}|{card['say']}".encode()).hexdigest()[:12],
        "kind": "question" if source else "deepen",
        "tag_key": source if entry else "question",
        "tag": label.removeprefix("Playbook · ") if entry else None,
        "title": " ".join(said["text"].split()[-TITLE_WORDS:]),
        "turn_ids": [said["id"]],
        "said_at": round(now, 1),
        "decision": None, "decision_note": None,
        "answer": card["say"], "fallback": None, "gap": None,
        "source": {"id": source, "label": label or brain.GENERIC_SOURCES.get(source, source)} if source else None,
        "repeated": False, "outcome": "open",
        "visible_t": round(now, 1),
    }


async def read_card(body: Any, ctx: Any) -> dict:
    """One reading at a checkpoint: {"type": "result", "producer": "card", "points": [the card] or [], "closed": [the card
    it replaces], "event", "moment", "read_t", "trace"} (the points result's shape, so the renderer merges it the same way)."""
    turns = [{"id": t.id, "who": t.who, "text": t.text, "t": t.t} for t in body.turns if t.text.strip()]
    result: dict[str, Any] = {"type": "result", "producer": "card", "state_version": body.state_version, "points": [], "closed": [],
                              "event": "", "moment": None, "read_t": None, "model": None, "latency_ms": None, "trace": {}}
    if not turns:
        result["event"] = "skipped:empty"
        return result
    end = ends(turns)
    now = end[-1]
    shown = sorted(({"id": c.id, "say": c.say, "visible_t": c.visible_t, "open": c.open} for c in body.cards), key=lambda c: c["visible_t"])
    moment = due(body.reason, body.objection, turns, end, now, body.last_read_t)
    result.update(moment=moment, read_t=round(now, 1))
    if moment is None:
        result["event"] = "skipped:not_a_moment"
        return result
    motion = (body.sales_motion_key or "").strip() or None
    sources = sources_text(ctx, motion)
    started = time.perf_counter()
    user = reading_input(sources, turns, end, now, shown)
    out, meta = await ask(SYSTEM, user, SCHEMA, max_tokens=TOKENS, temperature=0.2)
    trace: dict[str, Any] = {"reading": out, "reading_ms": meta["latency_ms"]}
    result.update(model=meta["model"], trace=trace)

    def finish(event: str) -> dict:
        result.update(event=event, latency_ms=int((time.perf_counter() - started) * 1000))
        return result

    if not out:
        result["error"] = meta["error"]
        return finish("error")
    if out.get("decision") != "card" or not (out.get("line") or "").strip():
        return finish("silence")
    if out.get("understanding_confidence") == "low":  # not sure what was meant (garbled, ambiguous, irony): no card
        return finish("low_confidence")
    card, why, checks = await vet(out, turns, end, now, shown, sources)
    trace.update(card=card["say"], checks=checks)
    if why == "repeats":  # the small gate saw the same move: one more try for a different one, or silence
        trace["repeat_of"] = card.get("same_as", "")
        retry, meta2 = await ask(SYSTEM, user + f"\n\nYOUR CARD «{card['say']}» REPEATS «{card.get('same_as', '')}», "
                                 "already shown, with nothing new from them since. Give a different next move that responds to what they "
                                 "said, or silence.", SCHEMA, max_tokens=TOKENS, temperature=0.2)
        trace["retry"] = retry
        if not retry or retry.get("decision") != "card" or not (retry.get("line") or "").strip() or retry.get("understanding_confidence") == "low":
            return finish("drop:repeats→silence")
        out = retry
        card, why, checks = await vet(out, turns, end, now, shown, sources)
        trace.update(card=card["say"], checks_retry=checks)
    if why:
        return finish(f"drop:{why}")
    floors_them = them_floors(turns, end)
    replaces = None
    if not rep_could_use(shown, turns, floors_them, now):
        if not can_update(shown, turns, floors_them, moment, now):
            return finish("drop:rep_has_last_card")
        replaces = shown[-1]["id"]
    labels = brain.allowed_sources(ctx.snapshot, has_knowledge=bool(ctx.knowledge), has_offer=bool(ctx.product_context),
                                   has_history=bool(ctx.history))
    result["points"] = [_card_point(card, body.call_id, turns, now, labels)]
    # One card on screen: whatever was still open fades where it is ("gone"), replaced or not.
    result["closed"] = [{"id": s["id"], "outcome": "gone"} for s in shown if s.get("open", True)]
    trace["replaces"] = replaces
    return finish("shown")
