"""The strategic card of the live call assistant (pilot, company flag LIVE_CARD_ENABLED): ONE intervention, or silence.

A port of the decision engine tried on Vocify's cold calls on 2026-10-28 (backend/evals/strategic/run_engine.py), on the
clock of turns-6b (when to read). The renderer sends the call and the cards already shown (the producer stays stateless,
like the points producer) and says why it reads; the code decides whether that is a moment to read at.

The rules only say how to read and decide, the same for any company: what was said comes before the playbook, then the
company's goals, then its criterion and situations (its own or Vocify's buenas prácticas, imported), then the approved
answers and the examples as ways to say things. Anything about selling lives in the playbook, not here.

- One reading: it weighs what is happening, what they said, what is only supposed, what is unknown and which of the
  company's situations fits, and writes their latest words, an action (clarify, deepen, answer, add value, next step,
  listen), what happens to the card on screen, and a card that rests on their own words, or silence (DeepSeek, strict
  JSON).
- Code checks what can be checked: at most 35 words, a fact cited from the playbook really is there, no number an
  answer invents, no weekday nobody said, not the same text as a card already shown, not after their goodbye.
- The small gate, in parallel: facts (only against the approved text and the conversation), the call closing, and a
  repeat of a move already made (one more try for a different move, or silence).
- The fact check also stops a question or proposal that goes against what they set or asks again what they answered.
- Pace: a card of the reading's own initiative not within MIN_GAP_S of the last one (a card that responds to what they
  just raised, or Responder, is not held back; it replaces another response only once that one is MIN_SWAP_S old), and the
  reading keeps the direction of the cards before until what they say contradicts or answers it.
- The screen holds one card. Until the rep could use it (REP_WORDS words of substance since it appeared, a new
  intervention of theirs begun and finished, or the rep closed it) each reading says whether it stays, is updated,
  replaced, made wrong by what they said (closed at once) or no longer the best (closed once it could be read). Never
  changed once the rep has started to speak.
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
from app.services.playbooks import conduct
from app.services.llm.shared import extract_json

logger = logging.getLogger(__name__)

PROMPT_VERSION = "strategic_engine_20261111_blanks"

# ---------- the prompts, word for word as tested (evals/strategic/run_engine.py) ----------
# The reading weighs what is happening, what was said, its hypotheses, what is unknown and the situation without writing
# them: it writes their latest words, then the move, then the card. Writing all of it took 1.3 s; this takes 0.8 s and
# decides the same (card or silence as the full reading on 44 of 60 moments, where the full reading agrees with itself on
# 42; production provider, 2026-11-11). The card first, or the card alone, was faster and decided worse (35 of 60).

SYSTEM = """You are the real-time sales copilot of a salesperson ("the rep", "You") in a call with a prospect ("Them").
You see the company's playbook and everything said so far.

Most moments need nothing from you: the rep is talking, listening or already handling it.

What you read has four levels. When they disagree, the higher level wins:
1. THE CONVERSATION and the fixed rules. What they said, what was agreed (a day, an email, a person), what they asked
   and is still unanswered, the limits they set. Facts about the product, prices, customers or results only from the
   SOURCES (OFFER, COMPANY KNOWLEDGE and the facts inside an approved answer). Never invent facts, commitments or
   actions the rep has not done; never contradict a day, a preference or a limit they set. When they ask something only
   the company can answer (how you got their contact, a price, a policy), that comes before anything else: answer it
   only from the SOURCES; when they do not say it, "silence" (the rep answers), never a card that goes on past it.
2. THE COMPANY'S GOALS: the goal of the call (with what else counts as good and when to stop pursuing it), WHAT TO FIND
   OUT and the STEPS. They say what the company wants to achieve and learn, not questions to ask in order: pursue them
   when this conversation makes them useful.
3. HOW THE COMPANY WANTS VOCIFY TO DECIDE: its general criterion and its situations, when present.
4. APPROVED ANSWERS and every example (of the steps, of the situations): ways to say things well. Use one when it fits
   this moment. Its facts count as a source; its tactic (pitching a capability, asking for a meeting now) is only a
   suggestion and never overrides levels 1 to 3. Never recite an example as is. When THEY JUST RAISED names an objection
   and its approved answer, the card answers that objection with it ("action" answer, "source" its id): the goal of the
   call comes after the answer, never instead of it. Use only the part of an approved answer that fits what they said;
   leave out the parts written for another case (a contract end date when they have no provider).

A DEMO: when the rep is showing Vocify to the other side and asks them to play an objection or a question so it can be
seen working («ponme una objeción», «suéltame una para que lo veas»), what they say next is the moment the demo is about.
Read it as a real objection or question and answer it like one, from the SOURCES and the approved answers: never
silence because it is staged or because the one who said it is a colleague and not a buyer. Outside a demo this
changes nothing.

How to decide. Steps 1 to 5 are what you weigh before answering: you do not write them. Your answer starts at step
6 and follows this order:
1. What is happening, and how sure you are of what they meant.
2. What they have actually said that matters now, in their words.
3. Your hypotheses: plausible readings you are not sure of. You may reason from them, but a card never states or
   presupposes them as facts: no question that takes for granted a failure, a loss or a gap they did not mention.
4. The most important thing still not known that could change the next commercial decision.
5. The situation: which of the company's SITUATIONS fits this moment, decided again now from what they have said, above
   all their latest words (often none fits, or there are no situations). When one
   fits, your action does what it says to do and nothing it says not to do.
6. "their_latest": what they just said, in a few words, and what it answers when it answers the last card or the rep's
   own move. A move already made is not made again, not even reworded; respond to their answer. THE THREAD shows the
   direction followed so far: keep it, each card building on the last, until what they said since contradicts it or
   has already answered it; then change direction. The same angle at most twice. "understanding_confidence" is "low"
   when the words are garbled, the meaning is ambiguous or it may be irony.
7. "action", the move that helps most now:
   - clarify: what they just said is ambiguous and the ambiguity changes how you read the opportunity;
   - deepen: understand how something works, what it gives them, what it costs when it happens or whether it is a
     priority, whichever matters now (no fixed order);
   - answer: they asked something; answer it first. About the seller's company or product only from the SOURCES; what a
     general term means or how something usually works, from common knowledge;
   - add_value: they have shown a concrete need the offer covers; connect only that part of the offer. A question that
     steers toward what the offer does is add_value too, and needs that need;
   - next_step: a step the rep would not think of on their own, that what they said calls for (bring in the person who
     decides, a visit they mentioned, who to send it to). Proposing the meeting, a day or a time to call is the rep's job:
     never a card for it;
   - listen: the rep is handling it, they are mid-explanation, or nothing is worth saying now.
   Persist while finding out still has value and they are receptive; change angle when one stops giving anything new;
   respect a clear no. When one of the company's situations describes this moment, act as it says. No checklist: a
   qualification question only when its answer matters for a decision now.
8. "card_on_screen": when a CARD ON SCREEN is listed, what happens to it given what was said since: "keep" (still the
   best move), "update" (same intention, its words are now out of date), "replace" (a materially better move appeared),
   "invalid" (what they just said makes it wrong: it contradicts them, they answered it or closed that topic),
   "withdraw" (no longer the best move and there is nothing better). "no_card" when none is listed.
9. "because": for a card, their words that make it the move now, copied exactly from what they said (at least three
   words); "" for silence. A card with no such words is not shown.
10. "decision": "card" only when there is something to show (a new card, an update or a replacement); otherwise
   "silence". "line" is then the card itself: the words the rep says, nothing else.

The card: one sentence the rep can say as is, in the language of the call, at most 20 words, natural and respectful,
built from their words. It is the rep's own words to them, never an instruction or a note about what to do («explorar
qué pasa…», «cambiar de la comparación a…»): the playbook's guidance tells you what to do, the card says it.
The company writes its examples with blanks in square brackets («Hola [cliente], soy [nombre] de…», «[cargo]», «[fecha]»)
and with one person's own details («Soy Toni, uno de los founders»). A card never has a bracket or a blank in it. Fill
one only with what THE CONVERSATION says (their name, their company, a date they gave); otherwise say the line without
that part. You are not told the rep's name: never write one, neither a blank nor the name in an example («Te llamo de
Movertis…», not «Soy [tu nombre] de Movertis…»), unless the conversation has called the rep by it.

Notes on the data: a fact about the product, prices, customers or results only when the SOURCES say it ("source": the
entry id as written before " · ", "offer" or "knowledge"; "source_quote": the verbatim text of the SOURCES); otherwise
"source" is "context" and "source_quote" is "". A card never proposes a day, a date or an hour: the rep agrees them with
the prospect. It may repeat one already said in the call, as the CALENDAR names it."""
SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "their_latest",
        "understanding_confidence",
        "action",
        "card_on_screen",
        "because",
        "decision",
        "line",
        "source",
        "source_quote"
    ],
    "properties": {
        "their_latest": {
            "type": "string"
        },
        "understanding_confidence": {
            "type": "string",
            "enum": [
                "high",
                "medium",
                "low"
            ]
        },
        "action": {
            "type": "string",
            "enum": [
                "clarify",
                "deepen",
                "answer",
                "add_value",
                "next_step",
                "listen"
            ]
        },
        "card_on_screen": {
            "type": "string",
            "enum": [
                "no_card",
                "keep",
                "update",
                "replace",
                "invalid",
                "withdraw"
            ]
        },
        "because": {
            "type": "string"
        },
        "decision": {
            "type": "string",
            "enum": [
                "card",
                "silence"
            ]
        },
        "line": {
            "type": "string"
        },
        "source": {
            "type": "string"
        },
        "source_quote": {
            "type": "string"
        }
    }
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
- General knowledge that is not about the seller's company, product or offer nor about the other side (what a common
  business term means, how something usually works in sales): fine when it is correct and commonly known.
- About the seller's company, team, people or product, or about what another product can do (who founded it, who does
  what, a capability, an integration, a figure, a customer, a result, why something is slow, recording the call): only
  the SOURCE (the company's approved text) supports it. The line may say less than the SOURCE or say it in other words;
  related is not enough.
- What the seller commits to is one of three things:
  · a fact or guarantee about the company or the product (it will work from tomorrow, a trial or access, a discount, a
    price, an integration): only the SOURCE supports it;
  · a proposal: a question or a suggestion of a next step («¿te llamo en enero?», «¿lo vemos el martes a las 10?»): it
    states nothing, fine when it fits the conversation; but it is unsupported when it goes against what the other side
    set or said (a date earlier than the one they gave, another channel or person than the one they named, whether
    their solution misses something they said it covers) or asks again what they already answered;
  · an action under the seller's own control (sending the information or an invitation, calling back, writing): fine
    when the seller can simply do it and it fits what was said («te mando la información hoy» after they asked for it).
    What it adds still needs THE CONVERSATION: a person nobody mentioned («con vuestra directora comercial»), or a date
    stated as already agreed («quedamos en enero») when they did not agree it.
- About the other side (their tools, team, situation, what they said or asked): THE CONVERSATION supports it. Naming a
  tool they said they use is not a claim about that tool.
  Their own description or guess of how the SELLER's product works is not a source. When the line confirms it as true
  («Exacto: Fireflies captura la transcripción y nuestro agente…» after they asked whether it works through Fireflies),
  the SOURCE must say it too: their having said it supports nothing about the product.
- Stating as done what the seller has not done («te acaba de llegar la invitación», «ya te lo he mandado») is a
  statement about the conversation: unsupported unless THE CONVERSATION shows it happened. Confirming a detail (a day,
  an hour, a name) that differs from what the other side said («lunes a las 10» when they said «11») contradicts it.
"unsupported" is also true when THE LINE is not words the salesperson can say as is to the other side: a note about
what to do («explorar qué pasa…», «ahora toca saber por qué…»), a label or a fragment.
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
goodbye one of them takes back («espera, una cosa más»). Not closing either: the other side putting the call off
without saying goodbye («llámame la semana que viene», «ahora estoy liado», «no puedo hablar ahora», «mándame un correo»,
«si nos interesa os llamamos»). That is pushback the salesperson can still answer (agree a day, ask one question); it
is closing only once a goodbye or a farewell wish has been said. Answer JSON {"closing": true|false, "evidence": "the words that
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
MIN_URGENT_SUBSTANCE = 2  # a question of theirs, or what the turn check flagged, is read with this many
MID_GAP_S = 40.0  # a long intervention is also read every this long while it goes on
REP_FLOOR_S = 45.0  # the rep holding the floor this long is a moment to read
REP_WORDS = 15  # the rep has had the chance to use the card on screen once they said this many words of substance
# A card on screen stays at least this long, unless what they said made it wrong: the rep reads it, says it and hears
# the answer. At 4 s a replay changed one card four times in 38 s while the prospect kept talking.
MIN_READ_S = 20.0
# A new card does not come within this long of the last one, unless they asked a question, raised an objection or the
# rep pressed Responder: five cards came in two minutes in a replay, more than a rep can use.
MIN_GAP_S = 30.0
# Both limits pace the cards the reading offers on its own initiative (deepen, add value, a next step). A card that
# responds to what they just raised is not held back by them: the reading's move is "answer" or "clarify", or the turn
# check or the code saw a question or an objection. The limits used to open only for what the turn check flagged, and it
# flagged neither «ya estamos trabajando con Granola» (its card came 27 s late, behind the 30 s) nor «¿cuántos sois en la
# empresa?» (no card: the one on screen was 10 s old). Real call, 2026-11-11.
RESPONDS = ("answer", "clarify")
# A response replaces at once a card of the reading's own initiative: a deeper question appeared 0.6 s before «me parece
# bastante caro» was read, and in a replay with one floor for every card the price went unanswered for 17 s and the next
# objection was lost behind its late answer. A card that was itself a response is given this long first: a flagged
# objection replaced a card of any age and one changed three times in 6 s while the same objection was still being said
# (real call, 2026-11-10).
MIN_SWAP_S = 8.0
# The same moment read twice: card one time and silence the other in 57 of 180 moments at 0.2, in 40 of 180 at 0 (14
# recorded calls, production provider, 2026-11-10). Lower, not gone: the provider is not deterministic at 0.
READ_TEMPERATURE = 0.0
TOKENS = 500  # a reading writes about 125 tokens, 236 at most in 60 moments: room to spare, never a cut answer
# The reading is asked for at most 20 words; only a clearly excessive card is refused (half the cards cut at 25 words
# were good ones of 26 to 31 words).
MAX_CARD_WORDS = 35
MIN_CARD_WORDS = 4  # «card», «their_latest» or a playbook id in the line is not a card
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
CALENDAR_DAYS = 28  # the days the reading sees with their weekdays
DAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
# The model turns-6b was tested with, on the direct provider; production's live help uses an older snapshot.
CARD_MODEL = "deepseek-ai/DeepSeek-V4.1-Flash-1017"
# Without an answer from the direct provider in this long, the backup starts too (Together stalls for 10-30 s at times).
HEDGE_S = 3.0
# The three checks answer in about 0.4 s: a stalled one is not waited for as long as a reading (13 of 686 rounds in
# production waited 3 s or more for the backup, and the card with them).
CHECK_HEDGE_S = 1.0
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
    - rep_turn: "rep_long" once the rep has held the floor REP_FLOOR_S, once per floor.
    - responder (the rep asked: "what do I say now?"): "asked", always."""
    if reason == "responder":
        return "asked"
    signals = listening(turns)
    held = floors(turns)
    last = last_read_t if last_read_t is not None else -1.0
    if reason in ("turn_end", "long_turn"):
        floor = next((f for f in reversed(held) if f["who"] == "them"), None)
        if floor is None:
            return None
        mine = own_turns(turns, floor, signals)
        if reason == "turn_end":
            said = sum(substance(turns[i]["text"]) for i in mine if end[i] > last)
            # A question of theirs is urgent even when the turn check missed it: it said «es caro, ¿no?» was no objection
            # in 2 of 3 tries, and the pace rule then left it unread.
            asked = "?" in turns[mine[-1]]["text"]
            urgent = bool(objection and objection != "none") or asked
            # A short question is read too: «¿Y exactamente qué es lo que hacéis?» and «¿Y qué precio tiene?»
            # have three words of substance and were never read, even flagged as a question (real call, 2026-11-11).
            # «¿Vale?» or «¿sabes?» alone still is not.
            if said < (MIN_URGENT_SUBSTANCE if urgent else MIN_SUBSTANCE):
                return None
            return "them_urgent" if urgent else "them_end"
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


LEVEL_NOTES = {
    "APPROVED ANSWERS (": "(Level 4: ways to answer. Their facts are a source; their tactic is only a suggestion.)",
    "STEPS (": "(Level 2: what the company wants each phase to achieve, not questions to ask in order.)",
    "WHAT TO FIND OUT (": "(Level 2: what is worth learning when it matters for a decision, not a list to ask.)",
}


def with_levels(sources: str) -> str:
    """A note under each playbook block saying its level in the reading's hierarchy. The headers stay as they are: the
    fact check finds the sources by them."""
    out = []
    for line in sources.splitlines():
        out.append(line)
        out += [note for header, note in LEVEL_NOTES.items() if line.startswith(header)]
    return "\n".join(out)


def sources_text(ctx: Any, motion: Optional[str]) -> str:
    """The SOURCES block: the playbook's goal as a starting point, the offer and the knowledge, the approved answers,
    the steps, what to find out and today's date (the same text the replays read). When the company wrote «Cómo
    trabajamos» for the type, its goal, other good outcomes, when to stop and its criteria replace the usual goal; they
    sit before every source block, so a card can never rest on them for a fact."""
    header = brain.playbook_header(ctx.snapshot, motion, None)
    company = conduct.brain_text(getattr(ctx, "conduct", None), brain.goal_for(motion))
    if company:
        header = header.split("\nGOAL:", 1)[0] + "\n" + company
    else:
        header = header.replace("GOAL:", "USUAL GOAL FOR THIS TYPE OF CALL (a starting point, not an obligation):", 1)
    return with_levels(header + "\n\n" + "\n\n".join([
        brain.context_blocks(product_context=ctx.product_context, knowledge=ctx.knowledge, history=ctx.history, call_text=""),
        brain.entries_block(ctx.snapshot) if ctx.snapshot else "",
        brain.steps_block(ctx.snapshot) if ctx.snapshot else "",
        brain.qualification_block(ctx.snapshot) if ctx.snapshot else "",
        ctx.today,
    ]))


def calendar(sources: str, days: int = CALENDAR_DAYS) -> str:
    """The next weeks with their weekdays, written by the code (a reading called 11 November a Tuesday)."""
    m = re.search(r"TODAY: \w+ (\d{4})-(\d{2})-(\d{2})", sources)
    if not m:
        return ""
    today = date(int(m[1]), int(m[2]), int(m[3]))
    return "CALENDAR: " + ", ".join(f"{DAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]}" + (" (hoy)" if d == today else "")
                                    for d in (today + timedelta(k) for k in range(days)))


_MONTHS_FULL = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre",
                "diciembre"]
_DAY_NUMBER = re.compile(r"\b(" + "|".join(DAYS) + r")\s+(\d{1,2})\b(?!\s*(?:minutos|min|horas|h)\b)(\s+de\s+(" + "|".join(_MONTHS_FULL)
                         + r"))?", re.IGNORECASE)
_HOUR_WORDS = "una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce"
_HOUR = re.compile(r"\s*\b(?:a las|a la)\s+(\d{1,2}|" + _HOUR_WORDS + r")(?:[:.](\d{2})|\s+y\s+(?:media|cuarto))?(?:\s*(?:h|horas)\b)?"
                   r"|\s*\b(\d{1,2}):(\d{2})(?:\s*(?:h|horas)\b)?", re.IGNORECASE)


# An hour as said in the call: «a las diez», «a partir de las 10», «las 10:30».
_HOUR_SAID = re.compile(r"\blas?\s+(\d{1,2}|" + _HOUR_WORDS + r")\b|\b(\d{1,2}):\d{2}\b", re.IGNORECASE)


def fixed_days(say: str, sources: str, said: str) -> str:
    """The card's days as the CALENDAR has them: a weekday with a date that is not that weekday in the next weeks keeps the
    weekday alone («el martes 12» on a Thursday 12 → «el martes»), and an hour nobody said in the call goes («el jueves
    a las 10:00» → «el jueves»). Readings wrote «martes 12» with the calendar in front of them, and invented the slot."""
    m = re.search(r"TODAY: \w+ (\d{4})-(\d{2})-(\d{2})", sources)
    today = date(int(m[1]), int(m[2]), int(m[3])) if m else None

    def day(match: re.Match) -> str:
        weekday, number, month = match[1], int(match[2]), (match[4] or "").lower()
        if today and any(d.day == number and DAYS[d.weekday()] == weekday.lower()
                         and (not month or _MONTHS_FULL[d.month - 1] == month)
                         for d in (today + timedelta(k) for k in range(CALENDAR_DAYS))):
            return match[0]
        # A date it cannot vouch for: the month it named stays («el martes 2 de junio» → «en junio»), else the weekday.
        return f"en {month}" if month else weekday

    out = _DAY_NUMBER.sub(day, say)
    out = re.sub(r"\b(?:el|la)\s+en\s+(" + "|".join(_MONTHS_FULL) + r")\b", r"en \1", out, flags=re.IGNORECASE)
    # An hour counts as said only when it was said as an hour («a las diez», «10:30»), not any number in the call: the rep's
    # «a diez minutos o a 300 kilómetros» let an invented «a las 10» through.
    hours = {n for h in _HOUR_SAID.finditer(said) for n in brain.numbers_in(h[1] or h[2])}
    out = _HOUR.sub(lambda h: h[0] if brain.numbers_in(h[1] or h[3]) <= hours else "", out)
    return re.sub(r"\s+([,.?!])", r"\1", " ".join(out.split()))


_WEEKDAY = re.compile(r"\b(" + "|".join(DAYS) + r")\b", re.IGNORECASE)


def proposed_day(say: str, said: str) -> bool:
    """The card names a weekday nobody said in the call («¿jueves o viernes?», «el martes 17» after «llámame la semana
    que viene»): the day is the rep's to agree. The prompt forbids it and readings still did it (6 of 120 on recorded
    moments, 2 of 35 cards in a replay of seven calls, 2026-11-11)."""
    heard = {d.lower() for d in _WEEKDAY.findall(said)}
    return any(d.lower() not in heard for d in _WEEKDAY.findall(say))


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


def spotted(objection: Optional[str], snapshot: Optional[dict]) -> str:
    """What the turn check saw in their last turn, for the reading: the objection and, when the playbook has one, its approved
    answer. The reading was never told, and answered «vale un pastón» with the meeting instead of the price answer."""
    if not objection or objection == "none":
        return ""
    entry_id = objection if objection.startswith("objection:") else f"objection:{objection}"
    entry = next((e for e in (snapshot or {}).get("entries") or []
                  if isinstance(e, dict) and e.get("entry_id") == entry_id and str(e.get("guidance") or "").strip()), None)
    if not entry:
        return f"\n\nTHEY JUST RAISED: an objection ({objection}). Answer it before anything else."
    name = entry.get("label") or entry.get("category") or objection
    return (f"\n\nTHEY JUST RAISED: «{name}». ITS APPROVED ANSWER ({entry_id}): {brain._clip(entry.get('guidance'), 600)}\n"
            "Answer this objection first, with the part of that answer that fits what they said, in their words; the next step "
            "comes after it, never instead of it.")


def reading_input(sources: str, turns: list[dict], end: list[float], now: float, shown: list[dict],
                  pending: Optional[dict] = None) -> str:
    # The renderer sends what has been said; nobody is mid-word in a transcript that has arrived.
    screen = (f"CARD ON SCREEN NOW (the rep has not used it yet): «{pending['say']}», shown at "
              f"{int(pending['visible_t'] // 60)}:{int(pending['visible_t'] % 60):02d}") if pending else "CARD ON SCREEN NOW: none"
    return (f"{sources}\n\n{calendar(sources)}\n\nLOG (\"You\" is the rep; [card shown] is a card the rep saw):\n"
            f"{log_text(turns, end, shown)}\n\nSPEAKING NOW:\n(nobody)\n\n{thread(turns, end, shown, now)}\n\n{screen}\n\n"
            f"NOW: {round(now)} s into the call.")


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


# A card that starts with one of these is a note to the rep, not words to say: the playbook's guidance is written as
# instructions and a replay showed «…explorar qué pasa cuando la duda surge en directo…» on screen.
NOTE_VERBS = {"explorar", "preguntar", "entender", "cambiar", "profundizar", "confirmar", "proponer", "agradecer",
              "conseguir", "presentar", "aclarar", "responder", "contestar", "ofrecer", "investigar", "indagar", "mantener",
              "evitar", "escuchar", "dejar", "explore", "ask", "understand", "confirm", "propose", "clarify", "offer"}


def says_as_is(say: str) -> bool:
    """The card reads as words to say, not as a note about what to do: no clause starts with an instruction verb."""
    clauses = re.split(r"[,:;.]\s*", say.strip().lstrip("¿¡«\"'("))
    return not any(c.split(" ", 1)[0].lower() in NOTE_VERBS for c in clauses if c)


def basic_checks(card: dict, turns: list[dict], shown: list[dict], sources: str) -> Optional[str]:
    if not card["say"].strip():
        return "no_evidence"
    if len(card["say"].split()) < MIN_CARD_WORDS or not says_as_is(card["say"]):
        return "not_a_line"
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
    if proposed_day(card["say"], " ".join(t["text"] for t in turns)):
        return "proposes_day"
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


def rests_on_their_words(out: dict, turns: list[dict]) -> bool:
    """The card names the words of theirs that make it the move now, copied from what they said. Before they have said
    anything there is nothing to rest on: the rep's own floor is the reason."""
    because = " ".join(str(out.get("because") or "").split())
    said = " ".join(t["text"] for t in turns if t["who"] == "them")
    if not said.strip():
        return True
    return len(because.split()) >= 3 and brain.quote_in(because, said)


# The rep pressed Responder: the same reading, told that help was asked for now. Silence stays possible, but a rep who asks
# wants the next move; the thread and the repeat check keep it from being the card already shown.
ASKED_NOTE = ("\n\nTHE REP ASKED YOU NOW («what do I say?»): give the next useful move from this conversation, an answer to "
              "what they just said or the next step toward the goal, not a move already made; silence only when nothing fits.")


ASKED_TRIES = 2  # more tries an asked reading gets after a dropped card; an automatic one gets one, only for a repeat


# ---------- the model ----------


async def _post(client: httpx.AsyncClient, url: str, headers: dict, payload: dict) -> str:
    resp = await client.post(url, headers=headers, json=payload)
    if resp.status_code >= 400:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
    content = ((resp.json().get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    if not content.strip():
        raise RuntimeError("empty answer")
    return content


async def ask(system: str, user: str, schema: dict, *, max_tokens: int, temperature: float,
              hedge_s: float = HEDGE_S) -> tuple[Optional[dict], dict]:
    """(parsed JSON or None, {"model", "latency_ms", "error"}): the direct provider with the tested model and a strict
    schema; OpenRouter as its backup, started after `hedge_s` without an answer or as soon as the direct one fails."""
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
                done, _ = await asyncio.wait(running, timeout=hedge_s if sources else None, return_when=asyncio.FIRST_COMPLETED)
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
    return await ask(FACT_SYSTEM, user, FACT_SCHEMA, max_tokens=700, temperature=0.0, hedge_s=CHECK_HEDGE_S)


async def closing_check(conversation: str) -> tuple[Optional[dict], dict]:
    return await ask(CLOSING_SYSTEM, f"THE LAST TURNS (latest last):\n{conversation or '-'}", CLOSING_SCHEMA, max_tokens=80, temperature=0.0,
                     hedge_s=CHECK_HEDGE_S)


async def repeat_check(say: str, shown: list[dict], turns: list[dict], end: list[float], at: float) -> tuple[Optional[dict], dict]:
    cards = "\n".join(f"- {int(s['visible_t'] // 60)}:{int(s['visible_t'] % 60):02d} «{s['say']}»" for s in shown)
    since = conversation_lines(turns, end, at, since=shown[-1]["visible_t"]) if shown else ""
    user = f"CARDS ALREADY SHOWN:\n{cards}\nSAID SINCE THE LAST CARD:\n{since or '(nothing)'}\nTHE NEW CARD: «{say}»"
    return await ask(REPEAT_SYSTEM, user, REPEAT_SCHEMA, max_tokens=120, temperature=0.0, hedge_s=CHECK_HEDGE_S)


async def _nothing() -> tuple[Optional[dict], dict]:
    return {"repeats": False, "same_as": "", "why": ""}, {"model": None, "latency_ms": 0, "error": None}


# ---------- one reading ----------


async def vet(out: dict, turns: list[dict], end: list[float], now: float, shown: list[dict], sources: str) -> tuple[dict, Optional[str], dict]:
    """The card the reading wrote, through the protections: (card, why it is dropped or None, what each check said)."""
    source = (out.get("source") or "").strip() or "context"
    quote = "" if source == "context" else (out.get("source_quote") or "")  # a line resting on the conversation quotes nothing
    line = (out.get("line") or "").strip()
    said = " ".join(t["text"] for t in turns)
    card = {"act": "answer" if source != "context" else "move", "say": fixed_days(line, sources, said), "source": source,
            "source_quote": quote}
    if card["say"] != line:
        card["days_fixed"] = line
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


def _card_point(card: dict, call_id: str, turns: list[dict], now: float, labels: dict[str, str], responds: bool = False,
                visible_t: Optional[float] = None) -> dict:
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
        "visible_t": round(now if visible_t is None else visible_t, 1),
        # Sent back with the cards shown: what replaces this card, and when, depends on it.
        "responds": responds,
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
    # The latest turn lasts until now. Its words alone do not say when now is: a turn that kept growing (both voices on
    # one side for minutes) stopped the clock at 49.6 s, every card came out "at 49.6" and sorted above newer ones.
    if body.now_t is not None:
        end[-1] = max(end[-1], body.now_t)
    now = end[-1]
    shown = sorted(({"id": c.id, "say": c.say, "visible_t": c.visible_t, "open": c.open, "responds": c.responds} for c in body.cards),
                   key=lambda c: c["visible_t"])
    moment = due(body.reason, body.objection, turns, end, now, body.last_read_t)
    floors_them = them_floors(turns, end)
    # The card the rep has not had the chance to use yet: the reading says whether it stays, changes or goes. Asked for,
    # a new card takes the screen.
    pending = shown[-1] if moment not in (None, "asked") and shown and not rep_could_use(shown, turns, floors_them, now) else None
    result.update(moment=moment, read_t=round(now, 1))
    if moment is None:
        result["event"] = "skipped:not_a_moment"
        return result
    motion = (body.sales_motion_key or "").strip() or None
    sources = sources_text(ctx, motion)
    started = time.perf_counter()
    user = (reading_input(sources, turns, end, now, shown, pending) + (ASKED_NOTE if moment == "asked" else "")
            + (spotted(body.objection, ctx.snapshot) if moment == "them_urgent" else ""))
    out, meta = await ask(SYSTEM, user, SCHEMA, max_tokens=TOKENS, temperature=READ_TEMPERATURE)
    trace: dict[str, Any] = {"reading": out, "reading_ms": meta["latency_ms"]}
    result.update(model=meta["model"], trace=trace)

    def finish(event: str) -> dict:
        result.update(event=event, latency_ms=int((time.perf_counter() - started) * 1000))
        return result

    if not out:
        result["error"] = meta["error"]
        return finish("error")
    status = (out.get("card_on_screen") or "no_card") if pending else "no_card"
    if pending and status == "no_card":  # a card on screen it did not account for: a new line replaces it
        status = "replace"
    trace["card_on_screen"] = status
    if pending and status in ("invalid", "withdraw"):
        # Wrong now (it contradicts them, they answered it): off at once. Only no longer the best: not before it was read.
        if status == "withdraw" and now - pending["visible_t"] < MIN_READ_S:
            return finish("keep:card_on_screen_too_new")
        result["closed"] = [{"id": pending["id"], "outcome": "gone"}]
        return finish(status)
    if pending and status == "keep":
        return finish("keep")
    if out.get("decision") != "card" or not (out.get("line") or "").strip():
        return finish("silence")
    if out.get("understanding_confidence") == "low":  # not sure what was meant (garbled, ambiguous, irony): no card
        return finish("low_confidence")
    if moment != "asked" and not rests_on_their_words(out, turns):
        return finish("drop:no_reason_in_their_words")
    # The card responds to what they just raised, or is the reading's own initiative: only the second is paced. A response
    # is what the reading's own move says is one, what the turn check flagged, or what the rep asked for. A «¿no?» at the
    # end of their sentence is not enough to take the screen: it let a deeper question replace an answer 1.3 s after it
    # appeared (real meeting, 2026-11-11). It still opens the 30 s gap, as before.
    flagged = bool(body.objection and body.objection != "none")

    def responding(reading: dict) -> bool:
        return moment == "asked" or flagged or reading.get("action") in RESPONDS

    responds = responding(out)
    if not pending and not (responds or moment == "them_urgent") and shown and now - shown[-1]["visible_t"] < MIN_GAP_S:
        return finish("drop:too_soon_after_last_card")
    if pending:
        # For the log: how old the card on screen is, what kind it is, and whether this client says which kind (a
        # dashboard loaded before 2026-11-11 does not).
        trace["on_screen"] = {"age_s": round(now - pending["visible_t"], 1), "responds": bool(pending.get("responds")),
                              "client_says_kind": any("responds" in c.model_fields_set for c in body.cards)}
    if pending:
        # A change: never once the rep has started to speak, nor before the card on screen could be read.
        if rep_said(turns, pending["visible_t"], now) >= 3:
            return finish("drop:rep_started_speaking")
        # A response is not kept waiting behind a card they have moved past (50 of the 226 cards dropped here in
        # production answered a flagged objection or question); the same card reworded ("update") waits like any other.
        if responds and status != "update":
            wait = MIN_SWAP_S if pending.get("responds") else 0.0
        else:
            wait = MIN_READ_S
        if now - pending["visible_t"] < wait:
            return finish("drop:card_on_screen_too_new")
    # An update keeps the intention of the card on screen: it is not checked as a repeat of it.
    against = [s for s in shown if s is not pending] if pending and status == "update" else shown
    card, why, checks = await vet(out, turns, end, now, against, sources)
    trace.update(card=card["say"], checks=checks)
    # Another try, told why: the same move again or a day nobody said (any reading: one more try), or, when the rep asked, also a
    # claim no source makes or the same words again (two more tries, each told every reason so far: a rep who pressed
    # Responder gets a move that stays inside what is written and is not one already made, rather than nothing).
    tries = ASKED_TRIES if moment == "asked" else 1
    notes = ""
    while why and tries > 0:
        if why == "same_text_as_shown" and moment == "asked":
            # Asked again, the same words are the same move: the rep wants another one.
            text = f"«{card['say']}»".lower()
            card["same_as"] = max(shown, key=lambda c: SequenceMatcher(None, text, f"«{c['say']}»".lower()).ratio())["say"]
            why = "repeats"
        if why == "repeats":
            trace["repeat_of"] = card.get("same_as", "")
            notes += (f"\n\nYOUR CARD «{card['say']}» REPEATS «{card.get('same_as', '')}», already shown, with nothing new from them "
                      "since. Give a different next move that responds to what they said, or silence.")
        elif why == "proposes_day":
            notes += (f"\n\nYOUR CARD «{card['say']}» NAMES A DAY NOBODY SAID IN THE CALL. The rep agrees the day with them: "
                      "make the same move without naming a day (ask which day suits them), or silence.")
        elif why == "unsupported_fact" and out.get("action") == "answer" and moment != "asked":
            # They asked and no source says it: an honest line, not silence (the older brain says «Te lo confirmo»).
            notes += (f"\n\nYOUR CARD «{card['say']}» STATES WHAT NO SOURCE SAYS. Their question is not answered in the SOURCES: "
                      "the line says honestly that the rep will confirm it («Eso te lo confirmo con el equipo técnico»), and may "
                      "add one question about their situation. It claims nothing about the product.")
        elif why == "unsupported_fact" and moment == "asked":
            what = ((checks.get("facts") or {}).get("what") or "").strip()
            notes += (f"\n\nYOUR CARD «{card['say']}» STATES WHAT NO SOURCE SAYS{f' ({what})' if what else ''}. Give a move that "
                      "claims nothing about the product beyond the SOURCES (a question about their situation, or a next step), or silence.")
        else:
            break
        tries -= 1
        retry, _ = await ask(SYSTEM, user + notes, SCHEMA, max_tokens=TOKENS, temperature=READ_TEMPERATURE)
        trace.setdefault("retries", []).append(retry)
        if not retry or retry.get("decision") != "card" or not (retry.get("line") or "").strip() or retry.get("understanding_confidence") == "low":
            return finish(f"drop:{why}→silence")
        out = retry
        card, why, checks = await vet(out, turns, end, now, against, sources)
        trace.update(card=card["say"], checks_retry=checks)
    if why:
        return finish(f"drop:{why}")
    replaces = pending["id"] if pending else None
    labels = brain.allowed_sources(ctx.snapshot, has_knowledge=bool(ctx.knowledge), has_offer=bool(ctx.product_context),
                                   has_history=bool(ctx.history))
    # The card appears when the reading ends, not when it was asked for: a reading of 4.1 s made its card look 4.1 s older
    # than it was to the next reading, and the 8 s it is given before another response replaces it were cut to 4.
    appears = now + (time.perf_counter() - started)
    result["points"] = [_card_point(card, body.call_id, turns, now, labels, responds=responding(out), visible_t=appears)]
    # One card on screen: whatever was still open fades where it is ("gone"), replaced or not.
    result["closed"] = [{"id": s["id"], "outcome": "gone"} for s in shown if s.get("open", True)]
    trace["replaces"] = replaces
    return finish(status if pending else "shown")
