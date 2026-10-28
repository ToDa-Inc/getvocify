"""The live brain experiment: what help does the rep need right now, if any, according to the company's strategy.

    cd backend && PATH=$HOME/.railway/bin:$PATH python -m evals.strategic.run_v2 --mode director --fast fast.json --out a.json
    python -m evals.strategic.run_v2 --mode unified --out b.json

Two modes, everything else equal (turns, memory, gate, pending opportunities):
- director (experiment A): a fast assistant answers questions and objections (its replay in --fast, through gate.py);
  this brain only directs. It sees every card the rep saw.
- unified (experiment B): this brain is the only assistant: it answers (from the approved sources) and directs.

How it works, and why:
- Help is an OPPORTUNITY, not a reaction to the last turn. A reading can answer now (an answer is urgent), propose a
  move now, or keep a move PENDING until it is the moment (the rep moves on without taking it) and drop it when the rep
  takes it or the conversation moves on. A move shows only when a later reading confirms it with what the rep did
  meanwhile in view (an opportunity that is real lasts beyond one reading), unless it rests on what they asked to be
  respected or a broken written rule. No fixed wait in words or seconds decides it: each reading does, on the whole
  context. PENDING_SAFETY_S only clears what a reading forgot to drop.
- Turns are semantic (turns.py): a «claro» or «mhm» while the other side talks is listening, not a turn; a reading
  starts when they finish an idea that is a question or objection (production's turn check) or says enough; while the
  rep talks, only when an opportunity is pending or the rep has talked a long while. One reading at a time.
- Memory is a log that only grows: the conversation, the brain's notes and the cards the rep saw, in order, never
  rewritten, so the provider reuses almost all of each prompt from its cache. What changes each time (the moment, the
  pending opportunities) comes after it.
- The gate (gate.py and below): no card over the other side; one move per exchange (after a move shows, the next waits
  until the other side has spoken again: the rep needs time to use it); an answer the rep already gave is not shown; an answer
  states nothing beyond its verbatim source quote; a move is re-checked by a small model just before it would show
  (the rep is not already doing it, it adds something, it does not go against what they asked); numbers never said in
  the call are refused.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
from pathlib import Path

import httpx

from evals.strategic import gate
from evals.strategic import turns as semantic
from evals.strategic.run import CALLS, PROSPECT_WORDS, RECENT_S, SECONDS_PER_WORD, context_for, ends, finished_by, words

MODEL = "deepseek-ai/DeepSeek-V4.1-Flash-1017"
PRICE = (0.30, 0.006, 1.20)  # $ per million tokens: input, cached input, output
MODES = ("director", "unified")
ANSWER_TOKENS = 900
MIN_WORDS, THEM_WORDS, REP_WORDS, CHUNK_WORDS, REP_STRETCH_S = 4, 12, 15, 12, 45.0
MAX_PENDING, PENDING_SAFETY_S = 3, 180.0
MOMENT_IDEAS = 2
SAME_OBJECTIVE = 0.8  # the gate copies the objective it names; this only absorbs small differences in the copy
# Together sometimes stalls for 10-30 s (measured 2026-10-22: a 20-token request took 15 s). Production starts its
# backup after 0.6 s without a word, so a stall does not reach the rep: in the replay's clock a reading takes at most
# this long. The measured latency is still recorded and reported.
CLOCK_LATENCY_CAP_S = 2.0
MAX_CARD_WORDS, SOURCE_QUOTE_WORDS, QUOTE_WORDS, SAME_TEXT = 25, 6, 3, 0.7
NOTE_TYPES = ["them_asked", "them_request", "fact", "rep_proposed", "rep_claim", "purpose", "closes", "need_confirmed", "need_ruled_out",
              "situation_change", "fit_open", "progress"]

SYSTEM = """You are the judgement of Vocify, a live assistant for a professional ("the rep", "You") in a conversation with
"the other side" ("Them"). Every time you read, you answer one question: what help does the rep need right now, if any?
Most of the time the answer is none.

"BETTER" IS THE COMPANY'S STRATEGY, NOT YOURS. Never impose your own sales methodology: the same move can be right for
one company and wrong for another. Combine three layers:
- GOAL: what this call is for (the PLAYBOOK's usual goal for this type of call), unless the conversation's purpose
  clearly changed (the person left the company, they are advising, they are already buying): then follow that.
- METHOD: how the company wants to sell: how hard to insist, when to ask for the meeting, how to handle each objection
  or limit, which questions come first. The PLAYBOOK holds four different things (WHAT THE PLAYBOOK IS FOR sorts them):
  · RULES (prices, promises, what is never said, anything written as mandatory): always respected.
  · OBJECTIVES (the goal, what each step and each data point is for): what you try to achieve, in the order the
    PLAYBOOK prefers, adapted to what has already happened.
  · TACTICS (how a step or an approved answer goes about it: how hard to insist, what to propose, which branch to try):
    preferred; when one does not fit what is happening, choose another way to reach the same objective that does not go
    against the company's method (when two entries pull different ways, the one that fits what they actually said wins).
  · EXAMPLES (a step's «Example», an answer's wording): another prospect's sentence, an illustration; never repeated as
    is unless the PLAYBOOK says it is mandatory.
  Playbooks are imperfect: a step may be incomplete, ambiguous, or count as done without its real objective being
  reached (they described how they work, but no need appeared). Judge by the objective, not by the checklist. Never
  ignore the PLAYBOOK, never recite it.
- CONTEXT: what the other side said and asked to be respected, what the rep is doing, what has already been tried
  (including the cards already shown), what options are still open.

{role}

HELP IS AN OPPORTUNITY, NOT A REACTION TO THE LAST TURN. An opportunity can be born while they talk and be right to
show later, when it would actually change what the rep does, or never, because the rep handles it. So:
- A new move has a "timing": "now" when it is clear and worth it at this moment and the rep is not already doing it
  (what they just said gives a pending objective a concrete opening; they asked or asked for something; the rep is
  going against a rule or talking over what they revealed): it is shown at once, even while the other side talks. The
  rep does not have to miss it first. "when_needed" only when its moment has not come yet (they are still developing
  the idea, the rep is clearly heading there): it waits in PENDING.
- Every reading decides each PENDING opportunity: "show_now" (its moment has come: the opening is there and the rep is
  not on it), "keep" (still valid, not the moment: they are still developing it, the rep is getting there), "drop" (the
  rep took it, even imperfectly; its objective was met; the conversation moved on and it would sound forced; it no
  longer fits the strategy).

LISTENING IS NOT REPLYING. Short acknowledgements of the rep while the other side talks («claro», «sí», «mhm»,
«total», «vale») are the rep listening well: never read them as ignoring something, and never break into the other
side's idea. Transcripts split speech at every change of voice: their idea may go on after the rep's «claro».

WHERE HELP COMES FROM. Every help names its "source", and the source decides what it must be:
1. The PLAYBOOK ("source": the entry's id exactly as written in SOURCES before " · ", e.g. objection:custom:no_me_interesa
   or an approved step's id): the approved answer for what they just said, or a step whose objective this moment can
   advance. An approved answer is used for what it resolves, keeping its tactic (how hard to push, what to propose)
   while that is still the situation; when the conversation is already past what it proposes (the demo is happening,
   the meeting is agreed), answer their concern without repeating that proposal. A step is used for its objective: its
   example is one way to get there; the line comes from their own words. What to do when they say no, ask to stop or end the call is also what the
   PLAYBOOK says (some companies accept the first no, others ask one more question); if it says nothing, judge it as 3.
2. The KNOWLEDGE or the OFFER ("source": "knowledge" or "offer"): a fact the rep needs, restating the SOURCES (with
   "source_quote").
3. The CONTEXT, your own judgement ("source": "context"): only when it passes this question: «Given this company's
   goal, method and priorities, is there a useful intervention that would improve what the rep is doing right now?»
   It must take the conversation to a better path from what they actually said: specific, natural, easy to say, often
   one short question about something concrete they just revealed that the rep is about to pass over. When the first
   hypothesis does not fit and their situation is changing, the useful question is often the one that clarifies an open
   point of fit for this product (what that change means for the conversations it helps with), never one that
   presupposes a pain; if the state already makes the fit clear either way, silence. Not this: a
   question that fits any call, a need they already ruled out, a next step the company does not use, telling the rep to
   close or leave, orders about the rep's manners.

STAY SILENT (even when a good question exists)
- The rep has said or is saying the same move (judge the intent of the rep's words). Do not wait to see whether the
  rep will do it: Vocify helps before the opportunity is lost, and a card does not force the rep to interrupt.
- A card already shown covers it (the log's [card shown] lines) and nothing new happened since: never the same card
  again. Pursuing the same objective again with the new information is not repeating (they rule out Thursday and
  Friday: a new day is a new card); asking what is already resolved is noise (the day is agreed: «¿qué día te encaja?»
  again is noise).
- An earlier topic once they are asking something else: a card answers what is on the table now.
- Interesting details on their own: a figure, their CRM or tools, a side topic they will handle later.
- Their personal life (why they left, where they are now, their health): never ask about it.
- They are explaining or advising on their own: let them talk.
- What the rep says about the company: the rep may know things the SOURCES do not; a claim missing from the SOURCES
  is not false. Say nothing unless it breaks a written PLAYBOOK rule.
- Obvious help the rep is already giving: introducing himself when he already did, explaining what you do while he
  is explaining it. Concretising a meeting they just offered (the day, the hour, the invite when the rep has not
  confirmed it) is not obvious help: it is the goal.

THE CARD IS ONE LINE (the rep sees only "line" and must know in one second what to do)
- A move is something the rep can SAY as is (at most 18 words): a question built from the other side's own words,
  neutral and natural, or a short proposal ("Te mando la info. ¿Lo
  vemos la semana que viene?"); or a short instruction when that is what helps (at most 8 words), about what to do in the conversation and said
  with respect: «Déjale terminar lo de las 2 horas», «No insistas esta semana». Never about the rep's manners and never
  rude («Cállate…», «Corta el rollo…»). It does not need to be sophisticated: choosing it at this moment is the
  intelligence. Prefer the line the rep can say as is: brief, natural, built from what they just said.
- A fact about the product, the offer, prices, customers or results only when it restates the SOURCES: then
  "source_quote" is the verbatim SOURCES text it rests on (at least 6 words) and the line says nothing beyond it.
  Without a source_quote the line states no fact.
- Never a menu of options, never a question that fits any call, never something already known or answered.
- The PLAYBOOK says what deserves attention; the card is still built from what they actually said. When an
  opportunity serves a PLAYBOOK step, do not fall back on the step's generic question («¿cómo lo tenéis montado?»):
  ask about the concrete thing they just told you, in their terms.
- "purpose" (what the card is for, at most 8 words, English) and "because" (at most 10 words, English) are internal.
- "objective": the commercial goal the card pursues, at most 6 words, English («get intro to the AI lead», «agree a
  demo date», «learn their ramp-up time»). When it pursues one listed under OBJECTIVES ALREADY PURSUED, copy that
  wording exactly. Pursuing an objective several times is the PLAYBOOK at work, not repetition: another card for the
  same objective helps when something relevant changed since (new information from them, a new constraint, the
  handling stalled or got lost), whatever its words. Asking again for what is already resolved, or going back to a
  hypothesis they ruled out, without new information, is noise.
- "help": "answer" (what they asked or objected, from the approved sources), "opportunity" (a question or move that
  takes the conversation to a better path from what they said), "correction" (the rep's own behaviour is going wrong:
  a long pitch, going against the PLAYBOOK, talking over what they revealed). An answer or an opportunity is shown as
  soon as it is clear and worth it, without waiting for the rep; a correction needs the behaviour to be visible.
- "useful_until": "rep_replies" (an answer, only useful until the rep has answered that question himself),
  "topic_changes" (useful while it is still relevant to what they are talking about: most moves), "call_ends" (a
  constraint or opportunity that stays valid, like a meeting they must leave for). A move does not stop being useful
  because the rep started talking.

THE LOG is the conversation with your earlier notes and the cards the rep saw, in order. Add NEW notes only for what
matters later (memory, not cards: a note shows nothing):
- them_asked: a real question from the other side, with "?" or a clear request (quote it). A statement is NOT a
  question. them_request: a limit or condition they set: end the call, no time now or this week, another channel or
  moment, an email instead, not to be named, already agreed to something (quote it). fact: something known about them,
  their team, tools, who decides (quote it). rep_proposed: something the rep proposed or asked for (quote it).
  rep_claim: a claim by the rep about the company that the SOURCES do not document or contradict (quote it; say
  which). purpose: the conversation's purpose changed (text only). closes: an earlier note no longer open: "closes" =
  its id. need_confirmed / need_ruled_out: a need, pain or use the product could serve that they confirmed, or ruled
  out for themselves (quote it; text says which need). situation_change: their commercial situation is changing (how
  they sell or acquire customers, their team, priorities, a project): quote it; text says what changes and what it may
  mean for the product (more fit, less fit, or unclear). fit_open: something that decides whether the product fits that
  is not known yet (text only, no quote: what is unknown; a question to clarify, not a pain). progress: the state
  of one of the OBJECTIVES moved (quote = the EVIDENCE, the words that show it, from either side, the rep included;
  text = its id exactly, then the state, then your INTERPRETATION in at most 12 words: «problema advancing: supervises
  the team himself; what he looks for is unknown»). States: "advancing" (there is evidence toward it, not enough yet),
  "met" (its "met when" is fully true: a meeting accepted without a day and a time is advancing, not met), "blocked"
  (they said something that stops it for now), "reopened" (something said undoes it after it was met).
- THE COMMERCIAL PROGRESS is evidence, interpretation and state, kept apart: «dedicates two hours to listening to
  calls» (evidence) → «supervises the team himself; we do not know yet what he looks for» (interpretation) → «need not
  confirmed yet; discovery open» (state). OBJECTIVES are reached by the conversation, not by reciting a step: either
  side can reach one (the prospect already knows the rep's track record: authority is met; the rep introduced himself
  and the call goes on: the opening is met; they ask for a demo: the goal is open now, whatever step was next).
  Activity is not progress: knowing their CRM is information, not a confirmed need; describing how they work is not a
  need. Only what has been said so far counts: a hypothesis opens when they say something real about their own
  situation, even if it turns out later not to fit. NOW shows each objective's state: never pursue one already met
  unless it was reopened.
- These notes are the commercial state: facts and revisable hypotheses about fit, not one verdict. A hypothesis they
  ruled out stays closed until they give new evidence for it; a new direction can be explored, and a conclusion can
  be revised when the conversation changes. They can all be
  true at once: «small experienced team» weakens the training angle, «less outbound, more brand» changes how they
  acquire customers, and how their sales conversations look now may still be open. A situation change is not a need
  ruled out: it may open a question that checks whether the product still fits, or it may reduce the fit. Never
  propose again a need they ruled out unless they reopen it; never force a new angle just because one was ruled out.
- Quotes are verbatim from one turn, 3 to 25 words. Text at most 10 words, in English. [] when nothing new matters
  (usual: most readings add nothing).

OUTPUT
- "opportunities": first, the commercial opportunities open right now (at most 4, most important first): the decision
  that comes after the state in NOW: which next move helps most toward the goal from what is known at this instant:
  asking, explaining, taking an opening for the demo, or silence. Each one pursues an objective: what they asked or asked for, the call's goal, or a pending objective of the PLAYBOOK (its
  steps and the data it wants). Order: what they asked or asked for first (a direct question; a demo they request is
  concretised even if earlier steps are missing); then the goal when there is clear interest; then the pending
  objective the conversation gives a concrete opening, in the PLAYBOOK's order by default. An objective already met is
  not an opportunity. When a branch of need is ruled out, another relevant branch, or recognising there is no fit;
  missing data (how many reps) is asked at a natural moment, never by derailing a meeting being closed. An opportunity
  the PLAYBOOK did not foresee can still matter if it fits the company's strategy. For each: "what" (at most 10 words,
  English), "serves" (the PLAYBOOK step or data id it serves as written in SOURCES, "goal" for the call's goal,
  "their_question" for what they asked, or "own" when it is your own reading), "priority": "act"
  (worth the rep's attention now: concrete, new, and the rep is not already on it), "follow" (keep in mind: it may
  matter later, or it is already moving), "no_action" (information to remember, a constraint, or a step already in
  motion between them). At most one is "act". Interesting information is not an opportunity by itself.
- "pending": one entry per PENDING opportunity listed under NOW (same id), with "decision" and "why" (at most 6
  words). [] when there is none.
- "new": at most one new help, and only for the opportunity marked "act" (none when nothing is "act"). "act" is "none" (usual) or one of the kinds your part allows. When "act" is "none",
  source, line, source_quote, purpose, objective, serves and because are "", evidence is [] and timing is "when_needed". "evidence": the note ids
  (n…) or turn ids (t…) it rests on. "serves": as in "opportunities". "basis": "example" (the line is a PLAYBOOK
  example nearly as written), "objective" (your own words for a PLAYBOOK objective), "answer" (an approved answer
  adapted) or "own" (your own reading). Never a new help that repeats a PENDING one: decide that one instead."""

ROLE = {
    "director": """YOUR PART: you direct. A fast assistant already answers, within a second, what the other side just asked or
objected, from the company's approved answers; its cards are in the log as [card shown]. You never write answers
("act" is "none" or "move"). You decide whether the rep should push, change tactic, go deeper, close, stop, or leave
it, according to the strategy. Come back to an objection the fast assistant answered only when the direction now needs
something different from its card (the same tactic was rejected, they repeated the no).""",
    "unified": """YOUR PART: you are the only assistant, so you give two kinds of help ("act" is "none", "answer" or "move"):
- ANSWER: they just asked something direct or raised an objection, and the rep needs the company's approved answer
  now. Find the PLAYBOOK entry or SOURCES text that covers it (that objection's approved answer, the offer, the
  knowledge) and adapt it to what they said, in one line the rep can say (at most 25 words), with "source_quote" the
  verbatim SOURCES text it rests on. Follow what the approved answer is for and its method (how hard to push, what to
  propose), not only its facts; when the conversation is already past what it proposes, answer the concern without
  repeating that proposal. An answer is shown at once ("timing" "now"): give it only when they have finished asking and the rep has
  not answered it yet. When no SOURCES text covers it, there is no answer: never invent one. Related content is not an
  answer: if the SOURCES talk about the topic but do not answer what they asked, there is no answer. Never answer what the rep
  obviously knows (who they are, their own company or team, where they are, a date or time): that is the rep's.
- MOVE: direction: whether the rep should push, change tactic, go deeper, close, stop, or leave it, according to the
  strategy, with its timing.""",
}


def schema(mode: str) -> dict:
    acts = ["none", "move"] if mode == "director" else ["none", "answer", "move"]
    return {
        "type": "object", "additionalProperties": False, "required": ["opportunities", "notes", "pending", "new"],
        "properties": {
            "opportunities": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["what", "serves", "priority"],
                "properties": {"what": {"type": "string"}, "serves": {"type": "string"},
                               "priority": {"type": "string", "enum": ["act", "follow", "no_action"]}}}},
            "notes": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                "required": ["type", "turn", "quote", "text", "closes"],
                "properties": {"type": {"type": "string", "enum": NOTE_TYPES}, "turn": {"type": "string"}, "quote": {"type": "string"},
                               "text": {"type": "string"}, "closes": {"type": "string"}}}},
            "pending": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["id", "decision", "why"],
                "properties": {"id": {"type": "string"}, "decision": {"type": "string", "enum": ["show_now", "keep", "drop"]},
                               "why": {"type": "string"}}}},
            "new": {"type": "object", "additionalProperties": False,
                "required": ["act", "help", "source", "line", "source_quote", "purpose", "objective", "serves", "basis", "because", "evidence", "timing", "useful_until"],
                "properties": {"act": {"type": "string", "enum": acts},
                               "help": {"type": "string", "enum": ["answer", "opportunity", "correction"]},
                               "source": {"type": "string"}, "line": {"type": "string"},
                               "source_quote": {"type": "string"},
                               "purpose": {"type": "string"}, "objective": {"type": "string"}, "because": {"type": "string"},
                               "serves": {"type": "string"}, "basis": {"type": "string", "enum": ["example", "objective", "answer", "own"]},
                               "evidence": {"type": "array", "items": {"type": "string"}},
                               "timing": {"type": "string", "enum": ["now", "when_needed"]},
                               "useful_until": {"type": "string", "enum": ["rep_replies", "topic_changes", "call_ends"]}}},
        },
    }


GATE_ASK = """GATE. A candidate help is ready for the rep: «{line}» (help: {help}; source: {source}; purpose: {purpose}; objective: {objective}).
Answer only this, not the reading's usual output. Judge it as a good sales manager of this company sitting next to the
rep, with only what has been said so far. Vocify is proactive: a card does not need the rep to have failed first.
Answer each question on its own:
- "correct": true to the SOURCES and the conversation; it states no data, commitment or fact they do not give; and the
  line is usable as written: brief, natural, respectful (an instruction says what to do, never «Cállate»), specific
  to what they said rather than a question that fits any call.
- "fits_playbook": it is how this company sells (PLAYBOOK, COMPANY METHOD), and the entry or tactic it uses matches what
  is really happening: the situation it assumes is the one they described. A good move the PLAYBOOK does not foresee
  fits if it serves the call's goal and goes against nothing in the PLAYBOOK.
- "adds": it gives the rep a next move the rep is not already making. Not the same move the rep has said or is
  saying (judge the intent of the rep's words, including SPEAKING NOW; a listening sound like «vale», «claro», «mhm»
  is neither doing it nor missing it); never wait to see whether the rep will do it. Not asking what is already
  resolved, not covered by a card already shown with nothing new since, not reopening what they ruled out without new
  evidence. Pursuing an objective again with new information adds. For an answer: it gives
  them what they actually asked or raised (the intent, not only the topic).
- "timing": "now" (their idea is clear and the moment is open; it can appear while they are still talking once their
  idea is clear); "not_yet" (their idea is not clear yet, or it corrects a behaviour not visible yet in the rep's
  words); "passed" (what it rests on was said a while ago and the conversation moved on, or it asks for what they already
  settled, like a day once the day is agreed). A meeting still being arranged is not passed: concretising it is now.
- "worth_interrupting": worth the rep's attention at this moment, weighing what it gives against distracting them. The
  question is whether it is a useful next move from what is known now, not whether it is the best one imaginable.
- "same_objective_as": the objective under OBJECTIVES ALREADY PURSUED that this card pursues too (the same commercial
  goal, even in other words: the same person's contact, the same date, the same hypothesis), copied exactly; "" when
  none. "relevant_change": when it pursues one, the words said after that card (by either side), verbatim, that make
  another card for it worth it (new information, the handling stalled or got lost); "" when nothing relevant changed.
- "their_words": the other side's words it rests on, verbatim. "rep_words": for a correction, the rep's words that show
  the behaviour, verbatim; "" otherwise.
- "why": at most 10 words: the question that failed, or why it is worth it."""
GATE_SCHEMA = {"type": "object", "additionalProperties": False,
               "required": ["correct", "fits_playbook", "adds", "timing", "worth_interrupting", "same_objective_as", "relevant_change",
                            "their_words", "rep_words", "why"],
               "properties": {"correct": {"type": "boolean"}, "fits_playbook": {"type": "boolean"}, "adds": {"type": "boolean"},
                              "timing": {"type": "string", "enum": ["now", "not_yet", "passed"]},
                              "worth_interrupting": {"type": "boolean"}, "same_objective_as": {"type": "string"},
                              "relevant_change": {"type": "string"}, "their_words": {"type": "string"},
                              "rep_words": {"type": "string"}, "why": {"type": "string"}}}
REASON_WORDS = 6  # what they revealed, asked or objected: a «Mhm. Okay. Claro.» is not a reason to interrupt


def grounded(out: dict, turns: list[dict], done: int, correction: bool) -> bool:
    """The gate's words, checked against what was said: their words really said by them; for a correction, the rep's
    words said after them (long rep turns arrive in pieces)."""
    from app.services.copilot.live_brain import quote_in

    theirs = " ".join(out["their_words"].split())
    said = [i for i, t in enumerate(turns[:done]) if t["who"] == "them" and len(theirs.split()) >= 3 and quote_in(theirs, t["text"])]
    if not said:
        return False
    if not correction:
        return True
    mine = " ".join(out["rep_words"].split())
    after = " ".join(t["text"] for t in turns[said[-1] + 1:done] if t["who"] == "you")
    return len(mine.split()) >= 3 and quote_in(mine, after)


def ask(system: str, user: str, effort: str, max_tokens: int, schema: dict, cache_key: str, temperature: float = 0.2) -> dict:
    payload = {
        "model": MODEL, "temperature": temperature, "max_tokens": max_tokens, "reasoning_effort": effort, "prompt_cache_key": cache_key,
        "response_format": {"type": "json_schema", "json_schema": {"name": "reading", "strict": True, "schema": schema}},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    last = None
    for attempt in range(3):
        t0 = time.perf_counter()
        try:
            r = httpx.post(os.environ["COPILOT_DIRECT_URL"], headers={"Authorization": f"Bearer {os.environ['COPILOT_DIRECT_API_KEY']}"},
                           json=payload, timeout=180)
            latency = time.perf_counter() - t0
            body = r.json()
            if r.status_code >= 400:
                raise RuntimeError(str(body)[:200])
            content = (body["choices"][0]["message"].get("content") or "").strip()
            usage = body.get("usage") or {}
            cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens") or usage.get("cached_tokens") or 0
            prompt, out = usage.get("prompt_tokens") or 0, usage.get("completion_tokens") or 0
            return {"parsed": json.loads(content), "latency": latency, "error": None, "prompt_tokens": prompt, "cached_tokens": cached,
                    "completion_tokens": out, "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0,
                    "cost": ((prompt - cached) * PRICE[0] + cached * PRICE[1] + out * PRICE[2]) / 1e6}
        except Exception as exc:  # retried; a reading that fails is recorded, never counted as silence
            last = repr(exc)[:200]
            time.sleep(5 * (attempt + 1))
    return {"parsed": None, "latency": 0.0, "error": last, "prompt_tokens": 0, "cached_tokens": 0, "completion_tokens": 0,
            "reasoning_tokens": 0, "cost": 0.0}


# ---------- when it reads ----------


def chunked(turns: list[dict]) -> list[dict]:
    """Long rep turns split into pieces of CHUNK_WORDS words with their own times, as a live transcript arrives, so a
    reading can happen while the rep is still talking (a replay turn of a minute arrives all at once)."""
    out = []
    for t in turns:
        ws = t["text"].split()
        if t["who"] != "you" or len(ws) <= 2 * CHUNK_WORDS:
            out.append(t)
            continue
        for k in range(0, len(ws), CHUNK_WORDS):
            out.append({**t, "id": f"{t['id']}.{k // CHUNK_WORDS + 1}", "t": t["t"] + k * SECONDS_PER_WORD, "text": " ".join(ws[k:k + CHUNK_WORDS])})
    return out


def read_moments(turns: list[dict], checks: dict[str, dict]) -> list[tuple[float, str]]:
    """(second, reason): "them_urgent" when the other side finished an idea that is a question or an objection (production's
    turn check: it has its own queue, see play), "them_idea" when it adds THEM_WORDS words; "rep" each time the rep said REP_WORDS words of substance since (read
    only while an opportunity is pending, or once REP_STRETCH_S of the rep talking has passed: see play). Listening
    signals count for neither."""
    end = ends(turns)
    ideas = set(semantic.idea_ends(turns, {k: v["finished"] for k, v in checks.items()}))
    signals = semantic.listening(turns)
    out, them_words, rep_words, flagged = [], 0, 0, False
    for i, t in enumerate(turns):
        if i in signals:
            continue
        if t["who"] == "them":
            them_words += len(semantic.tokens(t["text"]))
            flagged = flagged or (checks.get(t["id"]) or {}).get("objection", "none") != "none"
            if i in ideas and them_words >= MIN_WORDS and (flagged or them_words >= THEM_WORDS):
                out.append((end[i], "them_urgent" if flagged else "them_idea"))
                them_words, rep_words, flagged = 0, 0, False
        else:
            rep_words += semantic.substance(t["text"])
            if rep_words >= REP_WORDS:
                out.append((end[i], "rep"))
                rep_words = 0
    return out


# ---------- the log (memory that only grows) ----------


def log_text(turns: list[dict], upto: int, notes: list[dict], cards=(), end=()) -> str:
    """The conversation up to `upto` with each note after the turn it was written at, and each card the rep saw (as
    (second, line)) after the turn it appeared at: earlier text never changes."""
    after: dict[int, list[dict]] = {}
    for n in notes:
        after.setdefault(n["written_after"], []).append(n)
    screen: dict[int, list[str]] = {}
    for t, say in sorted(cards):
        at = finished_by(end, t) - 1
        if at < upto:
            screen.setdefault(at, []).append(say)
    lines = []
    for i, t in enumerate(turns[:upto]):
        lines.append(f"[{t['id']}] {'Them' if t['who'] == 'them' else 'You'}: {' '.join(t['text'].split())}")
        lines += [f"    [card shown] «{say}»" for say in screen.get(i, [])]
        for n in after.get(i, []):
            body = f"closes {n['closes']}" if n["type"] == "closes" else n["text"]
            quote = f" «{n['quote']}» ({n['quote_turn']}, {'Them' if n['who'] == 'them' else 'You'})" if n.get("quote") else ""
            lines.append(f"    [note {n['id']} {n['type']}]{quote} {body}".rstrip())
    return "\n".join(lines) or "(nothing said yet)"


def keep_notes(new: list[dict], turns: list[dict], upto: int, notes: list[dict]) -> list[dict]:
    """The new notes that hold: quotes really said by then (speaker from the turn), the right speaker for the type,
    `closes` pointing at an open note. Each is placed after the last turn the reading saw."""
    from app.services.copilot.live_brain import quote_in

    kept, ids = [], {n["id"] for n in notes}
    closed = {n["closes"] for n in notes if n["type"] == "closes"}
    for n in new or []:
        kind = n.get("type")
        note = {"type": kind, "text": " ".join(str(n.get("text") or "").split()[:20]), "written_after": upto - 1, "closes": ""}
        if kind == "closes":
            if n.get("closes") not in ids or n["closes"] in closed:
                continue
            note["closes"] = n["closes"]
        elif kind not in ("purpose", "fit_open"):  # objective_met / objective_reopened: either side's words  # these two are interpretations: text only
            quote = " ".join(str(n.get("quote") or "").split())
            found = [t for t in turns[:upto] if len(quote.split()) >= QUOTE_WORDS and quote_in(quote, t["text"])]
            if not found:
                continue
            turn = next((t for t in found if t["id"] == n.get("turn")), found[-1])
            if kind in ("them_asked", "them_request", "need_confirmed", "need_ruled_out", "situation_change") and turn["who"] != "them":
                continue
            if kind in ("rep_proposed", "rep_claim") and turn["who"] != "you":
                continue
            note.update(quote=quote, quote_turn=turn["id"], who=turn["who"], t=turn["t"])
        note["id"] = f"n{len(notes) + len(kept) + 1}"
        kept.append(note)
    return kept


def on_screen(shown, fast, now: float) -> list[tuple[float, str]]:
    """Every card the rep has seen by `now`, the fast assistant's and the brain's, as (second, line)."""
    return sorted([(t, say) for t, say in fast if t <= now] + [(s["visible_t"], s["say"]) for s in shown if s["visible_t"] <= now])


def moment(turns: list[dict], upto: int, end: list[float], now: float, reason: str) -> str:
    seen = turns[:upto]
    rep_r = sum(words(t["text"]) for i, t in enumerate(seen) if t["who"] == "you" and end[i] >= now - RECENT_S)
    them_r = sum(words(t["text"]) for i, t in enumerate(seen) if t["who"] == "them" and end[i] >= now - RECENT_S)
    stretch = 0
    for t in reversed(seen):
        if t["who"] == "them" and words(t["text"]) >= PROSPECT_WORDS:
            break
        if t["who"] == "you":
            stretch += words(t["text"])
    why = "the other side just finished an idea" if reason == "them_idea" else "the rep has been speaking"
    return (f"Elapsed {round(now)} s; {why}. Rep's share of words in the last {int(RECENT_S)} s: "
            f"{round(100 * rep_r / max(1, rep_r + them_r))}%. Rep's words since the other side last spoke at length: {stretch}.")


def pending_lines(pending: list[dict], turns: list[dict], upto: int, now: float) -> str:
    if not pending:
        return "(none)"
    out = []
    for o in pending:
        since = " ".join(' '.join(t["text"].split()) for t in turns[o["upto"]:upto] if t["who"] == "you")
        since = " ".join(since.split()[-40:]) or "(nothing)"
        out.append(f"- {o['id']} (born after {turns[o['upto'] - 1]['id']}, {round(now - o['born_t'])} s ago): «{o['say']}» "
                   f"— purpose: {o['purpose']}. The rep has said since: {since}")
    return "\n".join(out)


def speaking_now_lines(turns: list[dict], end: list[float], now: float) -> str:
    """The turns still in progress at `now`, with the words said so far (a live transcript arrives word by word): the
    log holds finished turns only, and the rep's first words often already show what they are doing."""
    out = []
    for i, t in enumerate(turns):
        if t["t"] <= now < end[i]:
            said = t["text"].split()[: max(1, int((now - t["t"]) / SECONDS_PER_WORD))]
            out.append(f"[{t['id']}] {'Them' if t['who'] == 'them' else 'You'} (speaking now): {' '.join(said)} …")
    return "SPEAKING NOW:\n" + ("\n".join(out) or "(nobody)")


def not_shown_lines(dropped: list[dict], now: float) -> str:
    recent = [d for d in dropped if now - d["born_t"] <= 120][-4:]
    return "\n".join(f"- «{d['say']}» ({d['why']})" for d in recent) or "(none)"


def reading_input(sources, turns, upto, notes, end, now, shown, fast, pending, reason, dropped=()) -> str:
    # Stable first: the sources, then the log, which only grows at its end. What changes every reading comes after it.
    closed = {c["closes"] for c in notes if c["type"] == "closes"}
    open_asks = [n for n in notes if n["type"] == "them_asked" and n["id"] not in closed]
    log = log_text(turns, upto, notes, on_screen(shown, fast, now), end)
    intent = INTENT.get(sources)
    return (f"{sources}{intent_block(intent)}\n\nLOG (\"You\" is the rep; your notes are indented; [card shown] is what the rep saw):\n{log}\n\n"
            f"NOW: {moment(turns, upto, end, now, reason)} Open questions from them: {', '.join(n['id'] for n in open_asks) or 'none'}."
            f"{objectives_now(notes, intent)}\n"
            f"PENDING opportunities:\n{pending_lines(pending, turns, upto, now)}\n"
            f"YOUR RECENT HELP NOT SHOWN (and why; do not propose it again unless the situation changed):\n{not_shown_lines(dropped, now)}\n"
            f"OBJECTIVES ALREADY PURSUED (by a card the rep saw; the last card for each):\n{objective_lines(shown, now)}")


def conversation_lines(turns: list[dict], end: list[float], now: float, n: int = 12, since: float | None = None,
                       chars: int = 3000) -> str:
    """The latest turns as the checks read them at second `now`: who said what, the seller's words included, and a
    turn still in progress with its words so far («ya estamos con Granola…» was being said when the card was written).
    With `since`, only turns that ended after that second."""
    lines = []
    for i, t in enumerate(turns):
        if t["t"] > now:
            break
        if since is not None and end[i] <= since:
            continue
        words = t["text"].split()
        if end[i] > now:
            words = words[: max(1, int((now - t["t"]) / SECONDS_PER_WORD))] + ["…"]
        lines.append(f"{'Seller' if t['who'] == 'you' else 'Other side'}: {' '.join(words)}")
    return "\n".join(lines[-n:])[-chars:]


def asserted(line: str) -> str:
    """The line without its questions: what it states."""
    import re

    line = re.sub(r"¿[^?]*\?", " ", line)
    return re.sub(r"[^.!]*\?", " ", line)


def offered(line: str) -> str:
    """What the line's questions offer to show about the product («¿te enseño cómo se rellenan solos?»): a capability
    taken for granted, judged as a statement. The checker read the question as stating nothing and let it through."""
    import re

    found = re.findall(r"(?:enseñ|muestr|explic)\w*[^?¿]*?\b(c[oó]mo\s[^?]+)", " ".join(re.findall(r"¿([^?]*)\?", line)))
    return " / ".join(f.strip() for f in found)


def call_over(at: float, call_end: float) -> bool:
    """A card ready after the call's last words has nobody to help."""
    return at > call_end


# How the other side closes a call, at the end of their turn. A mechanical end of the commercial moment, not a topic.
GOODBYES = ("hasta luego", "hasta mañana", "hasta pronto", "hasta otra", "adiós", "adios", "chao", "chau", "un saludo",
            "bye", "goodbye")
GOODBYE_TAIL_WORDS = 8  # the goodbye closes their turn: within its last words
AFTER_GOODBYE_SUBSTANCE = 4  # what they say after a goodbye that reopens the conversation


def after_goodbye(turns: list[dict], end: list[float], at: float) -> bool:
    """The other side said goodbye (a finished turn that ends with it) and has said nothing of substance since: the
    commercial moment is over even if the line is still open («…a ver si te podemos ver la semana que viene, ¿ok? Venga,
    hasta luego» and a card two seconds later)."""
    from evals.strategic.turns import substance

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


def answer_on_screen(card: dict, same_objective_as: str, shown: list[dict]) -> bool:
    """The same approved answer, for the same objective, is the card the rep still has on screen (nothing was shown
    since): them asking the same thing again is not new information, the rep already has the answer in front of them."""
    if card["act"] != "answer" or not shown or not same_objective_as.strip():
        return False
    last = shown[-1]
    same = SequenceMatcher(None, " ".join(same_objective_as.lower().split()), (last.get("objective") or "").lower()).ratio() >= SAME_OBJECTIVE
    return last.get("kind") == "answer" and last.get("source") == card.get("source") and same


def objective_lines(shown: list[dict], now: float) -> str:
    last: dict[str, dict] = {}
    for s in shown:
        if s.get("objective") and s["visible_t"] <= now:
            last[s["objective"]] = s
    return "\n".join(f"- {o} — last card at {int(s['visible_t'] // 60)}:{int(s['visible_t'] % 60):02d}: «{s['say']}»"
                     for o, s in last.items()) or "(none)"


def said_after(quote: str, turns: list[dict], done: int, ends: list[float], after: float, who: str | None = None) -> bool:
    """`quote` was said, verbatim, in a turn that ended after second `after` (by `who` when given). A quote the model
    stitched from several turns («… mándame un mail … no soy yo quien decide») counts when each piece was said."""
    import re

    from app.services.copilot.live_brain import quote_in

    pieces = [" ".join(p.split()) for p in re.split(r"\.\.\.|…", quote)]
    pieces = [p for p in pieces if len(p.split()) >= 3]
    return bool(pieces) and all(any(ends[i] > after and (who is None or t["who"] == who) and quote_in(p, t["text"])
                                    for i, t in enumerate(turns[:done])) for p in pieces)


# ---------- what the playbook is for (read once per playbook, before its calls) ----------

INTENT_SYSTEM = """You read a company's sales playbook once, before its calls, and sort what it says so a live assistant
can follow the company's strategy without reciting it. Playbooks are imperfect: steps are often written as what the rep
says or does, mix actions with results, or count as done without reaching their real purpose. Find the intention behind
each one, using only what the playbook says and the call's goal. Never add a sales method of your own. List EVERY
step and EVERY APPROVED ANSWER, with its id exactly as written.

- GOAL: "objective" (what the call is for) and "met_when" (what in the conversation shows it is reached).
- Each STEP (same id): "kind": "objective" when it pursues something in the conversation (credibility, a need, data, a
  meeting), "manner" when it is only about HOW the rep talks (listening, length, tone): a manner is not something to
  achieve. "objective": what the step is for, as a result in the conversation that moves toward the GOAL, not as an
  action of the rep (at most 15 words). When the step's criterion is an activity (the prospect described something,
  answered one question, the rep explained something), the objective is what that activity is for, not the activity:
  a description of how they work is there to find out whether there is a need the product solves; one answer about
  their tools is information, not a qualified opportunity. "met_when": what said by EITHER side shows the OBJECTIVE you
  wrote is reached, not the step's criterion: when the criterion is weaker than the objective (it counts an activity),
  follow the objective and say so in "playbook_notes" (the prospect can reach it too: they may already know the rep's
  track record) (at most 25 words). "tactics": how the playbook suggests getting there, as preferences that
  can adapt (at most 25 words, "" when none). "example_mandatory": true only when the playbook says its wording must be
  used as is.
- Each APPROVED ANSWER (same id): "resolves": what that answer is for (at most 12 words); "past_when": when the
  conversation is already past what it proposes, so repeating its proposal would not make sense (at most 15 words, ""
  when never).
- "rules": what the playbook makes mandatory or forbids (prices, promises, what is never said), each at most 20 words;
  [] when none.
- "playbook_notes": for the company, outside calls: steps that are ambiguous, incomplete, mix actions with results, or
  whose criterion counts as done without the objective (each at most 30 words); [] when none.
Write in the playbook's language."""

INTENT_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["goal", "steps", "answers", "rules", "playbook_notes"],
    "properties": {
        "goal": {"type": "object", "additionalProperties": False, "required": ["objective", "met_when"],
                 "properties": {"objective": {"type": "string"}, "met_when": {"type": "string"}}},
        "steps": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                  "required": ["id", "kind", "objective", "met_when", "tactics", "example_mandatory"],
                  "properties": {"id": {"type": "string"}, "kind": {"type": "string", "enum": ["objective", "manner"]},
                                 "objective": {"type": "string"}, "met_when": {"type": "string"}, "tactics": {"type": "string"},
                                 "example_mandatory": {"type": "boolean"}}}},
        "answers": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["id", "resolves", "past_when"],
                    "properties": {"id": {"type": "string"}, "resolves": {"type": "string"}, "past_when": {"type": "string"}}}},
        "rules": {"type": "array", "items": {"type": "string"}},
        "playbook_notes": {"type": "array", "items": {"type": "string"}},
    },
}
INTENT_DIR = Path.home() / ".vocify-evals" / "strategic-intent"
INTENT: dict[str, dict] = {}  # a call's SOURCES -> what its playbook is for (filled in main, once per playbook)


def playbook_part(sources: str) -> str:
    """The playbook in the SOURCES (goal, approved answers, steps, what to find out), without the call's own context."""
    blocks = source_blocks(sources)
    goal = next((line for line in sources.splitlines() if "GOAL" in line.split(":")[0]), "")
    return "\n\n".join([goal] + [blocks[h].split("\nTODAY:")[0].strip() for h in ("APPROVED ANSWERS", "STEPS (", "WHAT TO FIND OUT") if h in blocks])


def playbook_intent(sources: str) -> dict:
    """What the playbook is for, deduced once per playbook text and cached: the live readings only read it."""
    import hashlib

    part = playbook_part(sources)
    path = INTENT_DIR / f"{hashlib.sha256(part.encode()).hexdigest()[:16]}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    out = ask(INTENT_SYSTEM, part, "high", 16000, INTENT_SCHEMA, "intent", temperature=0)
    if not out["parsed"]:
        raise RuntimeError(f"the playbook could not be read: {out['error']}")
    # What to find out already says what a good answer is: taken as written, not read by the model.
    data = [{"id": line.split(" · ")[0].removeprefix("- "), "objective": line.split(" · ")[1].split(" — ")[0].strip(),
             "met_when": line.split("good answer:")[-1].strip() or "the other side says it"}
            for line in source_blocks(sources).get("WHAT TO FIND OUT", "").split("\nTODAY:")[0].splitlines()[1:] if line.startswith("- ")]
    intent = {**out["parsed"], "data": data}
    listed = {i["id"] for k in ("steps", "data", "answers") for i in intent[k]}
    missing = [line.split(" · ")[0].removeprefix("- ") for line in part.splitlines() if line.startswith("- ") and " · " in line
               and line.split(" · ")[0].removeprefix("- ") not in listed]
    if missing:
        raise RuntimeError(f"the playbook reading left out {missing}")
    INTENT_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({**intent, "cost": out["cost"]}, ensure_ascii=False, indent=1), encoding="utf-8")
    return intent


def intent_block(intent: dict | None) -> str:
    if not intent:
        return ""
    goal = intent["goal"]
    lines = ["\n\nWHAT THE PLAYBOOK IS FOR (read from the PLAYBOOK above, whose own text still rules)",
             f"GOAL → {goal['objective']} · met when: {goal['met_when']}", "OBJECTIVES (id → what it is for · met when · tactics, adaptable):"]
    for s in intent["steps"]:
        if s["kind"] == "objective":
            example = " · its example is mandatory wording" if s["example_mandatory"] else ""
            lines.append(f"- {s['id']} → {s['objective']} · met when: {s['met_when']}" + (f" · tactics: {s['tactics']}" if s["tactics"] else "") + example)
    lines += [f"- {d['id']} → {d['objective']} · met when: {d['met_when']}" for d in intent["data"]]
    manner = [s for s in intent["steps"] if s["kind"] == "manner"]
    if manner:
        lines.append("MANNER (how the rep talks; not objectives, never a card on their own): "
                     + "; ".join(f"{s['id']} → {s['objective']}" for s in manner))
    lines.append("APPROVED ANSWERS BY PURPOSE (id → what it resolves · past it when):")
    lines += [f"- {a['id']} → {a['resolves']}" + (f" · past it when: {a['past_when']}" if a["past_when"] else "") for a in intent["answers"]]
    lines.append("RULES (mandatory): " + ("; ".join(intent["rules"]) or "none beyond the PLAYBOOK's text"))
    return "\n".join(lines)


def objective_ids(intent: dict | None) -> list[str]:
    if not intent:
        return []
    return ["goal"] + [s["id"] for s in intent["steps"] if s["kind"] == "objective"] + [d["id"] for d in intent["data"]]


PROGRESS_STATES = ("advancing", "met", "blocked", "reopened")


def objectives_now(notes: list[dict], intent: dict | None) -> str:
    """Each objective's commercial progress from the progress notes: its state, the interpretation and the evidence
    (the latest note for each); the ones with none are pending."""
    ids = objective_ids(intent)
    if not ids:
        return ""
    last: dict[str, tuple[str, str, dict]] = {}
    for n in notes:
        if n["type"] != "progress":
            continue
        words = (n.get("text") or "").replace(":", " : ").split()
        if len(words) < 2 or words[0].strip(".,;") not in ids or words[1].strip(".,:;") not in PROGRESS_STATES:
            continue
        rest = " ".join(words[2:]).lstrip(": ").strip()
        last[words[0].strip(".,;")] = (words[1].strip(".,:;"), rest, n)
    rows = []
    for oid in ids:
        if oid not in last:
            continue
        state, why, n = last[oid]
        state = "advancing" if state == "reopened" else state
        rows.append(f"- {oid}: {state.upper()} — {why} (evidence: «{n['quote']}», {'Them' if n['who'] == 'them' else 'You'})")
    pending = [i for i in ids if i not in last]
    return ("\nCOMMERCIAL PROGRESS (state — interpretation (evidence)):\n" + ("\n".join(rows) or "(nothing yet)")
            + f"\nNo evidence yet: {', '.join(pending) or 'none'}.")


def playbook_example(sources: str, card: dict) -> bool:
    """The line is a PLAYBOOK example or a sentence of an approved answer nearly as written: measured here, not asked to
    the model (it labelled «Déjale hablar: ¿Cómo lo tenéis montado ahora?», the step's own example, as its own words).
    Nearly as written: at least 75% of that sentence's words are in the line and they are at least half of the line."""
    import re

    def words_of(text: str) -> list[str]:
        return re.findall(r"[a-záéíóúüñ0-9]+", text.lower())

    say = words_of(card["say"])
    blocks = source_blocks(sources)
    texts = re.findall(r"Example: «([^»]+)", blocks.get("STEPS (", ""))
    texts += [line.split(": ", 1)[-1] for line in blocks.get("APPROVED ANSWERS", "").splitlines()[1:]]
    for sentence in (x for t in texts for x in re.split(r"(?<=[.?!])\s+", t)):
        ws = words_of(sentence)
        shared = sum(1 for w in ws if w in say)
        if len(ws) >= 4 and shared >= 0.75 * len(ws) and shared >= 0.5 * len(say):
            return True
    return False


# ---------- the gate for this brain's cards ----------


def entry_line(sources: str, source: str) -> str:
    """The whole SOURCES line of a playbook entry or step by its id («- objection:timing · …»), or "" when there is none."""
    source = source.strip()
    if not source or source in ("context", "knowledge", "offer"):
        return ""
    for line in sources.splitlines():
        if line.strip().startswith(f"- {source} ·") or line.strip().startswith(f"{source} ·"):
            return line.strip().removeprefix("- ")
    return ""


def entry_text(sources: str, source: str) -> str:
    return entry_line(sources, source)[:700]


SOURCE_BLOCKS = ("OFFER (", "COMPANY KNOWLEDGE (", "EARLIER CALLS", "APPROVED ANSWERS", "STEPS (", "WHAT TO FIND OUT")
LINE_BLOCKS = ("APPROVED ANSWERS", "STEPS (", "WHAT TO FIND OUT")  # one entry per line: a quote points at its line


def source_blocks(sources: str) -> dict[str, str]:
    """{block header: the whole block} of the SOURCES text."""
    starts = sorted((sources.find(h), h) for h in SOURCE_BLOCKS if h in sources)
    return {h: sources[i:(starts[k + 1][0] if k + 1 < len(starts) else len(sources))].strip() for k, (i, h) in enumerate(starts)}


def authorized_text(sources: str, card: dict) -> str:
    """The whole approved source a card rests on: its playbook entry or step (by its id), the offer or the knowledge, and
    the entry or block where its quote is found. Numbers and facts are checked against this, not against the fragment the
    model copied (a fragment cut before «15 minutos» made the approved answer look invented)."""
    from app.services.copilot.live_brain import quote_in

    blocks = source_blocks(sources)
    source = (card.get("source") or "").strip()
    quote = " ".join((card.get("source_quote") or "").split())
    parts = [blocks.get("OFFER (", "") if source == "offer" else blocks.get("COMPANY KNOWLEDGE (", "") if source == "knowledge"
             else entry_line(sources, source)]
    if len(quote.split()) >= SOURCE_QUOTE_WORDS:
        for header, block in blocks.items():
            if header in LINE_BLOCKS:
                parts += [line.strip().removeprefix("- ") for line in block.splitlines() if quote_in(quote, line)]
            elif quote_in(quote, block):
                parts.append(block)
    return "\n".join(dict.fromkeys(part for part in parts if part))


def card_text(card: dict) -> str:
    return f"«{card['say']}»"


def basic_checks(card, notes, turns, upto, shown, fast, sources: str) -> str | None:
    from app.services.copilot.live_brain import numbers_in, quote_in

    known = {n["id"] for n in notes} | {t["id"] for t in turns[:upto]}
    if not card["say"].strip() or not any(e in known for e in card["evidence"]):
        return "no_evidence"
    if len(card["say"].split()) > MAX_CARD_WORDS:
        return "too_long"
    quote = " ".join((card.get("source_quote") or "").split())
    card["authorized"] = authorized_text(sources, card)
    # An answer needs an approved source it rests on (its entry, the offer or the knowledge); a move that cites one too.
    if (card["act"] == "answer" or quote) and not card["authorized"]:
        return "source_not_found"
    # In an answer, a number it states that neither the call nor its approved source has is a fact it would be inventing.
    # A number inside a question proposes («¿te llamo mañana a las 9?»), it states nothing; a claim smuggled into a
    # question is the fact check's.
    if card["act"] == "answer" and numbers_in(asserted(card["say"])) - numbers_in(" ".join(t["text"] for t in turns[:upto]) + " " + card["authorized"]):
        return "invented_number"
    text = card_text(card).lower()
    if any(SequenceMatcher(None, text, f"«{say}»".lower()).ratio() > SAME_TEXT for _, say in on_screen(shown, fast, 1e9)):
        return "same_text_as_shown"
    return None


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
# The whole conversation so far (a call of 10-20 minutes fits): what they said minutes ago backs a line now («se lo
# reenviaré a la directora comercial» at 3:08, the invitation with her at 6:42).
FACT_TURNS, FACT_CHARS = 400, 12000
FACT_EFFORT = "none"  # tried "low": it did not catch more and blocked a supported answer
FACT_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["unsupported", "what"],
               "properties": {"unsupported": {"type": "boolean"}, "what": {"type": "string"}}}


STATE_SYSTEM = """A live assistant already showed a salesperson a card for a commercial objective. It now wants to show
another card for the SAME objective. Did the state of that objective change since the earlier card, so that another
card for it is worth it? A change: the other side gave a new availability, alternative or condition, accepted or
refused, asked for something else instead (an email, another moment), a new person or decision-maker appeared, they
revealed something new about themselves or their situation that bears on it, a new concern or need appeared that bears
on it, or the attempt was dropped and the moment to pick it up again has come.
Not a change: agreement or listening sounds («sí, sí», «vale», «claro»), repeating what was already said, talk about
something else, or only the salesperson talking. Answer JSON {"changed": true|false, "evidence": "the words that show
the change, copied verbatim from ONE turn said after the earlier card (at most 20 words); empty when nothing changed"}."""
STATE_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["changed", "evidence"],
                "properties": {"changed": {"type": "boolean"}, "evidence": {"type": "string"}}}


CLOSING_SYSTEM = """Is this sales call closing? Closing: the two sides are wrapping up and nothing new is being opened:
goodbyes or farewell wishes, thanking and leaving, confirming the last step and ending. Either side closing
unequivocally is enough, even before the other answers: the other side says goodbye, or the salesperson closes («pues
te deseo mucha suerte», «que vaya muy bien, un abrazo»), unless the other side then reopens with something new. Not
closing: agreeing a next step while the conversation goes on, a thank-you in the middle of the call, a
goodbye one of them takes back («espera, una cosa más»). Answer JSON {"closing": true|false, "evidence": "the words that
show it, copied verbatim from ONE of the last turns; empty when not closing"}."""
CLOSING_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["closing", "evidence"],
                  "properties": {"closing": {"type": "boolean"}, "evidence": {"type": "string"}}}
CLOSING_TURNS = 8
CLOSING_RECENT_S = 30.0  # the words that show the call is closing were said in its last half minute


def closing_check(conversation: str, cache_key: str) -> dict:
    """The end of the call as a state of the conversation, either side closing and the other going along (a list of
    goodbye words missed «te deseo mucha suerte» — «gracias», and a card came after it)."""
    return ask(CLOSING_SYSTEM, f"THE LAST TURNS (latest last):\n{conversation or '-'}", "none", 80, CLOSING_SCHEMA,
               f"{cache_key}-closing", temperature=0.0)


def closing_confirmed(result: dict | None, turns: list[dict], end: list[float], now: float) -> bool:
    """The check says the call is closing and its evidence was really said in the last CLOSING_RECENT_S seconds."""
    import re

    from app.services.copilot.live_brain import quote_in

    if not result or not result.get("closing"):
        return False
    said = []  # what each recent turn had said by `now` (a turn in progress only up to its words so far)
    for i, t in enumerate(turns):
        if t["t"] > now:
            break
        if end[i] > now - CLOSING_RECENT_S:
            words = t["text"].split()
            said.append(" ".join(words if end[i] <= now else words[: max(1, int((now - t["t"]) / SECONDS_PER_WORD))]))
    pieces = [" ".join(p.split()) for p in re.split(r"\.\.\.|…", result.get("evidence") or "")]
    pieces = [p for p in pieces if len(p.split()) >= 1]
    return bool(pieces) and all(any(quote_in(p, x) for x in said) for p in pieces)


def state_check(objective: str, earlier: str, conversation_since: str, cache_key: str) -> dict:
    """Whether a commercial objective a card already pursued has moved since (words appearing after that card are not
    enough: «Sí, sí, ya se ha podido ver» let a second identical demo proposal through)."""
    user = f"OBJECTIVE: {objective}\nEARLIER CARD: «{earlier}»\nSAID SINCE THAT CARD (latest last):\n{conversation_since or '(nothing)'}"
    return ask(STATE_SYSTEM, user, "none", 80, STATE_SCHEMA, f"{cache_key}-state", temperature=0.0)  # a check: same answer every time


def fact_check(card: dict, cache_key: str, conversation: str = "") -> dict:
    """An answer states nothing its approved source does not (the model embellished answers when unchecked: «Gonzalo y yo
    fundamos Vocify», «sí, la grabo»). About 0.3 s; tested on 45 answers it caught all 8 invented facts."""
    source = card.get("authorized") or card.get("source_quote") or "(none: this line has no approved source)"
    # What the line states outside its questions, separated by code: the model read «Con Excel no hay integración que
    # montar: ¿qué campos…?» as one question and let the statement through.
    stated = " ".join(asserted(card["say"]).split()).strip(" .:;,")
    user = (f"SOURCE: «{source}»\nTHE CONVERSATION (latest last):\n{conversation or '-'}\nTHE LINE: «{card['say']}»\n"
            f"WHAT THE LINE STATES OUTSIDE ITS QUESTIONS: «{stated or '(nothing: only questions)'}»"
            + (f"\nWHAT ITS QUESTIONS OFFER TO SHOW THE PRODUCT DOING (a claim, judged like a statement): «{offered(card['say'])}»"
               if offered(card["say"]) else ""))
    return ask(FACT_SYSTEM, user, FACT_EFFORT, 700, FACT_SCHEMA, f"{cache_key}-facts", temperature=0.0)  # a check: same answer every time


# ---------- one call ----------


def play(call: dict, mode: str, sources: str, fast=(), custom: dict | None = None) -> dict:
    turns = chunked(call["turns"])
    end = ends(turns)
    moments = read_moments(turns, semantic.turn_readings(call, custom))
    cache_key = f"brain-{mode}-{call['id']}"
    notes: list[dict] = []
    readings, shown, pending, dropped = [], [], [], []
    clock, spent, next_id = 0.0, 0.0, 1

    def show(card: dict, at: float, how: str, check: dict | None = None):
        done = finished_by(end, at)
        shown.append({"visible_t": round(at, 1), "after_turn": turns[max(0, done - 1)]["id"], "kind": card["act"], "say": card["say"],
                      "source": card.get("source", ""),
                      "source_quote": card.get("source_quote", ""), "purpose": card["purpose"], "objective": card.get("objective", ""),
                      "serves": card.get("serves", ""), "basis": card.get("basis", ""), "because": card["because"],
                      "playbook_example": playbook_example(sources, card),
                      "born_t": card["born_t"], "how": how, "gate": check, "gates": card.get("gates") or [],
                      "rests_on_t": rests_on(check, done),
                      # From the end of what they said that the card rests on to the card on screen.
                      "reaction_s": round(at - max((end[i] for i, t in enumerate(turns) if t["who"] == "them" and end[i] <= card["born_t"] + 1e-6),
                                                   default=card["born_t"]), 1)})

    def rests_on(check: dict | None, done: int) -> float | None:
        """When the other side finished the words the gate says the card rests on (None when they cannot be found)."""
        from app.services.copilot.live_brain import quote_in

        quote = " ".join(((check or {}).get("their_words") or "").split())
        hits = [end[i] for i, t in enumerate(turns[:done]) if t["who"] == "them" and len(quote.split()) >= 3 and quote_in(quote, t["text"])]
        return round(hits[-1], 1) if hits else None

    def display(card: dict, at: float) -> str:
        """Is there room for it now. An answer always has room (urgent: never behind anything); an opportunity or a
        correction waits until the rep has had the chance to use the card on screen. An approved card is not judged
        again: it waits for room or a reading drops it. Nothing is shown once the call is over."""
        if call_over(at, end[-1]):
            return "drop:call_over"
        if after_goodbye(turns, end, at):
            return "drop:after_goodbye"
        if card.get("approved_t") is not None and ideas_since(card["approved_t"], at) > 0:
            return "drop:stale"  # approved but waited for room while the conversation moved on: no longer this moment
        if card["help"] != "answer" and not rep_used_last(at, card["help"]):
            card.setdefault("approved_t", at)
            return "keep:approved"
        show(card, at, card["help"], card["approved"])
        return "shown"

    def try_show(card: dict, ready: float, reason: str) -> str:
        """The value gate (and, for an answer, the fact check at the same time): "shown", "keep" or "drop:<why>"."""
        nonlocal spent
        done = finished_by(end, ready)
        prompt = (reading_input(sources, turns, done, notes, end, ready, shown, fast, pending, reason, dropped) + "\n"
                  + speaking_now_lines(turns, end, ready) + "\n\n"
                  + GATE_ASK.format(line=card["say"], help=card["help"], source=card.get("source") or "context", purpose=card["purpose"],
                                  objective=card.get("objective") or "-"))
        jobs = {"gate": lambda: ask(SYSTEM.replace("{role}", ROLE[mode]), prompt, "none", 260, GATE_SCHEMA, cache_key)}
        # Every card, answer or move, has what it states checked: a move can promise a trial or invent a cause as well.
        # A question states nothing and passes. The conversation is the source for facts about the other side.
        jobs["facts"] = lambda: fact_check(card, cache_key, conversation_lines(turns, end, ready, n=FACT_TURNS, chars=FACT_CHARS))
        # Is the call closing (either side wrapping up and the other going along)? Alongside the others: no extra wait.
        jobs["closing"] = lambda: closing_check(conversation_lines(turns, end, ready, n=CLOSING_TURNS), cache_key)
        with ThreadPoolExecutor(max_workers=3) as pool:
            got = {k: f.result() for k, f in {k: pool.submit(fn) for k, fn in jobs.items()}.items()}
        spent += sum(g["cost"] for g in got.values())
        # An answer goes on screen as soon as it is written: the gate and the fact check run alongside, and a rejection
        # takes it away before the rep can read it (counted here as not shown). Anything else appears after the gate.
        checked = ready + min(max(g["latency"] for g in got.values()), CLOCK_LATENCY_CAP_S)
        at = ready if card["act"] == "answer" else checked
        out = got["gate"]["parsed"]
        card.setdefault("gates", []).append(out)
        if "facts" in got and (got["facts"]["parsed"] or {"unsupported": True})["unsupported"]:
            return "drop:unsupported_fact"
        if closing_confirmed(got["closing"]["parsed"], turns, end, ready):
            return "drop:call_closing"
        if not out:
            return "drop:gate_failed"
        # One question each, in this order; the first that fails is the reason.
        if not out["correct"]:
            return "drop:not_correct"
        if not out["fits_playbook"]:
            return "drop:off_playbook"
        if not out["adds"]:
            return "drop:adds_nothing"
        if out["timing"] == "passed":
            return "drop:too_late"
        if out["timing"] == "not_yet" and card["act"] == "answer":
            return "drop:answer_not_now"  # an answer is worth it right after what they asked, not later
        if not out["worth_interrupting"]:
            return "drop:not_worth_interrupting"
        if out["timing"] == "not_yet" or not grounded(out, turns, finished_by(end, at), card["help"] == "correction"):
            return "keep"
        if any(SequenceMatcher(None, card_text(card).lower(), f"«{say}»".lower()).ratio() > SAME_TEXT for _, say in on_screen(shown, fast, at)):
            return "drop:same_text_as_shown"
        done_at = finished_by(end, at)
        # The same commercial objective as a card already shown: only when the state of that objective changed since,
        # shown by words said after that card (new words alone are not a change).
        mine = " ".join(out["same_objective_as"].lower().split())
        earlier = [s for s in shown if mine and SequenceMatcher(None, mine, (s.get("objective") or "").lower()).ratio() >= SAME_OBJECTIVE]
        if earlier:
            last = earlier[-1]
            state = state_check(last.get("objective") or mine, last["say"], conversation_lines(turns, end, at, since=last["visible_t"]), cache_key)
            spent += state["cost"]
            at += min(state["latency"], CLOCK_LATENCY_CAP_S)  # asked after the gate: the card waits for it
            done_at = finished_by(end, at)
            st = state["parsed"] or {"changed": False, "evidence": ""}
            card["state"] = st
            if not st["changed"] or not said_after(st["evidence"], turns, done_at, end, last["visible_t"]):
                return "drop:same_objective"
        if answer_on_screen(card, out["same_objective_as"], shown):
            return "drop:answer_on_screen"
        # A card held back is shown later only if its opportunity is still alive: once the other side has moved on, what
        # it rests on must have been said after it was written.
        if ideas_since(card["born_t"], at) > 0 and not said_after(out["their_words"], turns, done_at, end, card["born_t"], "them"):
            return "drop:moment_passed"
        card["approved"] = out
        return display(card, at)

    them_ideas = [t for t, r in moments if r.startswith("them")]

    def rep_used_last(at: float, help_kind: str = "opportunity") -> bool:
        """The rep has had the chance to use the last card: they said REP_WORDS words of substance since it appeared, or
        the other side finished an idea. Two cards seconds apart cannot both be used. A correction on screen never holds
        back an opportunity (what they revealed matters more than how the rep is pitching)."""
        if not shown:
            return True
        if help_kind == "opportunity" and shown[-1]["kind"] == "move" and shown[-1]["how"] == "correction":
            return True
        last = shown[-1]["visible_t"]
        return ideas_since(last, at) > 0 or gate.rep_said(turns, last, at) >= REP_WORDS

    def ideas_since(t0: float, t1: float) -> int:
        return sum(1 for t in them_ideas if t0 < t <= t1)

    last_read = -1e9
    while moments:
        # A question or an objection has its own queue: it is read the moment they finish, never behind a reading in flight.
        start = moments[0][0] if moments[0][1] == "them_urgent" else max(clock, moments[0][0])
        due = [r for t, r in moments if t <= start]  # what happened meanwhile is read in this one reading
        moments = [(t, r) for t, r in moments if t > start]
        reason = "them_idea" if any(r.startswith("them") for r in due) else "rep"
        if reason == "rep" and not pending and start - last_read < REP_STRETCH_S:
            continue
        last_read = start
        upto = finished_by(end, start)
        for o in list(pending):
            # Each opportunity's own window: one useful only before the rep replies is gone once they have.
            # Only an answer is gone once the rep has answered it himself; a move lasts while it is relevant (the reading
            # and the gate decide that), not until the rep starts talking.
            gone = (o["act"] == "answer" and o["useful_until"] == "rep_replies"
                    and gate.rep_said(turns, end[o["upto"] - 1], start) >= REP_WORDS)
            # A card that never reached the screen loses its moment once the other side has moved on by MOMENT_IDEAS
            # ideas (unless it stays valid all call): a card shown a minute after what it rests on reads as noise.
            gone = gone or (o["useful_until"] != "call_ends" and ideas_since(o["born_t"], start) >= MOMENT_IDEAS)
            if gone or start - o["born_t"] > PENDING_SAFETY_S:  # PENDING_SAFETY_S: a safety net, readings decide
                pending.remove(o)
                dropped.append({**o, "why": "window_passed" if gone else "expired"})
        result = ask(SYSTEM.replace("{role}", ROLE[mode]), reading_input(sources, turns, upto, notes, end, start, shown, fast, pending, reason, dropped),
                     "none", ANSWER_TOKENS, schema(mode), cache_key)
        spent += result["cost"]
        ready = start + min(result["latency"], CLOCK_LATENCY_CAP_S)
        out = result["parsed"]
        entry = {"start_t": start, "reason": reason, "upto": upto, "after_turn": turns[upto - 1]["id"], "error": result["error"],
                 **{k: result[k] for k in ("latency", "prompt_tokens", "cached_tokens", "completion_tokens", "cost")},
                 "output": out, "notes_kept": 0, "events": []}
        readings.append(entry)
        clock = max(clock, ready)
        if not out:
            continue
        added = keep_notes(out.get("notes"), turns, upto, notes)
        notes.extend(added)
        entry["notes_kept"] = len(added)
        # The generator decides each pending opportunity; the ones it wants on screen go to the show gate.
        attempts = []
        decisions = {d["id"]: d for d in out.get("pending") or []}
        for o in list(pending):
            d = decisions.get(o["id"])
            if d and d["decision"] == "drop":
                pending.remove(o)
                dropped.append({**o, "why": f"reading: {d['why']}"})
                entry["events"].append(f"{o['id']} dropped")
            elif d and d["decision"] == "show_now":
                attempts.append(o)
        new = out["new"]
        if new["act"] != "none":
            card = {"id": f"o{next_id}", "act": new["act"], "source": new["source"].strip(), "method": entry_text(sources, new["source"]),
                    "say": new["line"].strip(), "source_quote": new["source_quote"],
                    "purpose": new["purpose"], "objective": new["objective"].strip(), "serves": new["serves"], "basis": new["basis"],
                    "because": new["because"], "evidence": new["evidence"], "born_t": start, "upto": upto,
                    "useful_until": new["useful_until"], "help": "answer" if new["act"] == "answer" else new["help"]}
            next_id += 1
            if card["act"] == "answer" and not authorized_text(sources, card):
                card.update(act="move", help="opportunity")  # a question with no source to rest on is a move, not an answer
            problem = basic_checks(card, notes, turns, upto, shown, fast, sources)
            if not problem and any(SequenceMatcher(None, card_text(card).lower(), card_text(o).lower()).ratio() > SAME_TEXT for o in pending):
                problem = "same_as_pending"
            if not problem and card["source"] not in ("context", "knowledge", "offer") and not card["method"]:
                problem = "unknown_playbook_source"
            if problem:
                dropped.append({**card, "why": problem})
                entry["events"].append(f"new {problem}")
            else:
                pending.append(card)
                entry["events"].append(f"{card['id']} pending")
                # Proactive: an answer or an opportunity goes to the gate at once; a correction waits until a later
                # reading sees the rep's behaviour and asks to show it.
                if card["help"] != "correction":
                    attempts.insert(0, card) if card["help"] == "answer" else attempts.append(card)
        attempts += [o for o in pending if o.get("approved") and o not in attempts]
        for o in attempts:
            if o not in pending:
                continue
            what = display(o, ready) if o.get("approved") else try_show(o, ready, reason)
            if what == "drop:stale":
                pending.remove(o)
                dropped.append({**o, "why": what})
                continue
            entry["events"].append(f"{o['id']} {what}")
            if what == "shown":
                pending.remove(o)
                break  # one card per reading: the rep can use one
            if what.startswith("drop"):
                pending.remove(o)
                dropped.append({**o, "why": what})
        while len(pending) > MAX_PENDING:
            dropped.append({**pending.pop(0), "why": "too_many_pending"})
    dropped += [{**o, "why": "still_pending_at_end"} for o in pending]
    return {"id": call["id"], "mode": mode, "readings": readings, "shown": shown, "notes": notes, "dropped": dropped,
            "duration": end[-1], "cost": spent}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--mode", choices=MODES, required=True)
    parser.add_argument("--only", required=True, help="comma-separated call ids")
    parser.add_argument("--fast", help="director mode: the fast assistant's replay (run_fast), shown through gate.py")
    parser.add_argument("--out", required=True)
    parser.add_argument("--prod-turn-check", action="store_true",
                        help="give the turn check the playbook's own objections, as production does")
    parser.add_argument("--live-playbook", action="store_true", help="read the company's live playbook, not the call's pinned version")
    parser.add_argument("--playbook-extra", help="a file with the company's method added to every call's PLAYBOOK")
    args = parser.parse_args()
    if args.mode == "director" and not args.fast:
        sys.exit("director mode needs --fast: the fast assistant's replay")
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from evals.copilot.run import load_production_provider

    load_production_provider()
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    calls = [json.loads((CALLS / f"{c}.local.json").read_text(encoding="utf-8")) for c in args.only.split(",")]
    # One at a time: the database client is shared. The playbook's goal is presented as the usual one, not an order.
    contexts = [context_for({**c, "playbook_version_id": None} if args.live_playbook else c).replace("GOAL:", "USUAL GOAL FOR THIS TYPE OF CALL (a starting point, not an obligation):", 1) for c in calls]
    if args.playbook_extra:
        rule = Path(args.playbook_extra).read_text(encoding="utf-8").strip()
        contexts = [f"{c}\n\nCOMPANY METHOD (part of the PLAYBOOK: how this company wants to sell):\n{rule}" for c in contexts]
    custom = None
    if args.prod_turn_check:
        from app.services.copilot.playbook_objections import custom_entries
        from app.services.playbooks.live import live_snapshot
        from evals.copilot.export_calls import supabase

        custom = custom_entries(live_snapshot(supabase(), calls[0]["company_id"], calls[0]["motion"]))
    for c in calls:
        semantic.turn_readings(c, custom)  # asked once, before the threads
    for ctx in contexts:  # what each playbook is for, read once (cached by the playbook's text)
        INTENT[ctx] = playbook_intent(ctx)
    fast = {cid: shown for cid, (shown, _dropped) in gate.fast_screen([c["id"] for c in calls], args.fast).items()} if args.fast else {}
    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        played = list(pool.map(lambda pair: play(pair[0], args.mode, pair[1], [(c["t"], c["say"]) for c in fast.get(pair[0]["id"], [])], custom),
                               zip(calls, contexts)))
    # What the rep saw: this brain's cards and, in director mode, the fast assistant's, in order.
    for p in played:
        p["brain_shown"] = [{**s, "producer": "brain"} for s in p["shown"]]
        p["shown"] = sorted(p["brain_shown"] + [gate.as_shown(c) for c in fast.get(p["id"], [])], key=lambda s: s["visible_t"])
    Path(args.out).write_text(json.dumps({"mode": args.mode, "version": "3.7", "model": MODEL, "fast": args.fast, "played": played},
                                         ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    for p in played:
        rs = [r for r in p["readings"] if not r["error"]]
        lat = sorted(r["latency"] for r in rs)
        hit = sum(r["cached_tokens"] for r in rs) / max(1, sum(r["prompt_tokens"] for r in rs))
        mins = p["duration"] / 60
        kinds = [s["kind"] for s in p["brain_shown"]]
        react = sorted(s["reaction_s"] for s in p["brain_shown"] if s["kind"] == "answer")
        print(f"{p['id']}: {len(p['readings'])} readings ({len(p['readings']) - len(rs)} errors, {len(p['readings']) / mins * 30:.0f} per 30 min); "
              f"shown {len(kinds)} (answers {kinds.count('answer')}, moves {kinds.count('move')}); latency p50 {lat[len(lat) // 2] if lat else 0:.1f} s "
              f"p90 {lat[int(len(lat) * 0.9)] if lat else 0:.1f} s; answers on screen {react} s after they finished; "
              f"cache {hit:.0%}; ${p['cost']:.3f} = ${p['cost'] / mins * 30:.3f} per 30 min")
    return 0


if __name__ == "__main__":
    sys.exit(main())
