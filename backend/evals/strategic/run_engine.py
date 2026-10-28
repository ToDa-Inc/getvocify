"""The decision engine of 2026-10-28 (eval only), next to turns-6b (run_turns) to compare them on the same calls.

What changes, and why (three cold calls of Vocify read card by card):
- One hierarchy: what was said in the call and the fixed rules first, then the company's goals (the goal, what to find
  out, the steps as aims, not questions in order), then how it wants Vocify to decide (its criterion and situations),
  last the approved answers and every example as ways to say things. An approved answer's facts are still a source; its
  tactic (pitch a capability, ask for a slot now) no longer beats what the prospect set (a card offered two other days after
  the prospect had set one, from the «Envíame un correo» answer).
- The reading separates what was observed, plausible hypotheses (reasoned from, never stated as facts) and what is still
  unknown («nada relevante ahora» is an answer), then picks an action: clarify, deepen, answer, add value, next step or
  listen.
- The card on screen is reconsidered at every reading: keep, update (same intention, new words), replace (a materially
  better move) or withdraw, never once the rep has started to speak nor before it could be read (MIN_READ_S). A reading
  while the prospect is still talking may change it too (a card stayed up for a minute while the prospect moved on
  to other tools and how the team copes). A cap of one change per intervention lost a better question; it is gone.
- Every card names the words of theirs that make it the move now, copied from the call, or it is not shown.
- Round 2 (same day): playing something down is not a no; the offer's own capability («during the meeting») only
  against a need they showed; the situations' and the Problema step's examples left out (they were copied where they
  did not fit); general knowledge allowed in an answer («¿qué es un SDR?» went unanswered), the product still only
  from the SOURCES.
- The playbook lines that pushed presupposing or scripted cards are reworded in memory (REWORDED); the playbook itself
  is not touched.
- The turn check is asked again with two fixes (turn_checks): not recognising the caller is not «not now», and the
  team's own objection only when they say that thing.
- Round 3 (same day): a card made wrong by what they said goes at once, one that is only no longer the best stays until
  it could be read; no interest with a reason is not an objection to explore (no demo after a no explained by
  an acquisition); no question about a limit of their current solution they did not describe; how you got their contact is
  answered only from the SOURCES, otherwise left to the rep.
- Round 5: the brain only holds how to read and decide, the same for any company; what is about selling (telling a no
  with a reason from a lack of time, playing something down, the offer's capability only against a need, where their
  contact came from) moved to the playbook as Vocify's buenas prácticas (app/services/playbooks/practices.py).
- Round 6: before deciding, the reading names which of the company's situations fits (or none) and follows it: moved to
  the playbook, the practices were followed less than the same words as rules of the brain.
- Round 4: the fact check also stops a question or proposal that goes against what they set or said, or asks again
  what they answered (a sooner month than the «in six months» they gave); before, a proposal passed as stating nothing.
"""

from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from evals.strategic import gate
from evals.strategic import run_turns as rt
from evals.strategic import run_v2 as v2
from evals.strategic import turns as semantic
from evals.strategic.run import ends, finished_by
from evals.strategic.run_min import calendar, thread
from app.services.copilot.live_brain import quote_in

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
   suggestion and never overrides levels 1 to 3. Never recite an example as is.

How to decide (your answer follows this order):
1. "what_is_happening"; "understanding_confidence" is "low" when the words are garbled, the meaning is ambiguous or it
   may be irony.
2. "observed": what they have actually said that matters now, each point with their words.
3. "hypotheses": plausible readings you are not sure of. You may reason from them, but a card never states or
   presupposes them as facts: no question that takes for granted a failure, a loss or a gap they did not mention.
4. "unknown": the most important thing still not known that could change the next commercial decision, or "nada
   relevante ahora".
5. "situation": which of the company's SITUATIONS fits this moment, from everything they have said (its number and
   name), or "none" (often none fits, or there are no situations). When one fits, your action does what it says to do
   and nothing it says not to do.
6. "their_latest", then "last_move": the last card or the rep's own move on this and what they answered. A move already
   made is not made again, not even reworded; respond to their answer.
7. "action", the move that helps most now:
   - clarify: what they just said is ambiguous and the ambiguity changes how you read the opportunity;
   - deepen: understand how something works, what it gives them, what it costs when it happens or whether it is a
     priority, whichever matters now (no fixed order);
   - answer: they asked something; answer it first. About the seller's company or product only from the SOURCES; what a
     general term means or how something usually works, from common knowledge;
   - add_value: they have shown a concrete need the offer covers; connect only that part of the offer. A question that
     steers toward what the offer does is add_value too, and needs that need;
   - next_step: there is interest; a concrete next step that respects what they already set;
   - listen: the rep is handling it, they are mid-explanation, or nothing is worth saying now.
   Persist while finding out still has value and they are receptive; change angle when a line stops giving anything new;
   respect a clear no. When one of the company's situations describes this moment, act as it says. No checklist: a
   qualification question only when its answer matters for a decision now.
8. "card_on_screen": when a CARD ON SCREEN is listed, what happens to it given what was said since: "keep" (still the
   best move), "update" (same intention, its words are now out of date), "replace" (a materially better move appeared),
   "invalid" (what they just said makes it wrong: it contradicts them, they answered it or closed that topic),
   "withdraw" (no longer the best move and there is nothing better). "no_card" when none is listed.
9. "because": for a card, their words that make it the move now, copied exactly from what they said (at least three
   words); "" for silence. A card with no such words is not shown.
10. "decision": "card" only with a line to show (a new card, an update or a replacement); otherwise "silence".

The card: one sentence the rep can say as is, in the language of the call, at most 20 words, natural and respectful,
built from their words.

Notes on the data: a fact about the product, prices, customers or results only when the SOURCES say it ("source": the
entry id as written before " · ", "offer" or "knowledge"; "source_quote": the verbatim text of the SOURCES); otherwise
"source" is "context" and "source_quote" is "". For days use the CALENDAR."""

SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["what_is_happening", "understanding_confidence", "observed", "hypotheses", "unknown", "situation", "their_latest",
                 "last_move", "action", "card_on_screen", "because", "decision", "line", "source", "source_quote"],
    "properties": {
        "what_is_happening": {"type": "string"},
        "understanding_confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "observed": {"type": "string"}, "hypotheses": {"type": "string"}, "unknown": {"type": "string"},
        "situation": {"type": "string"},
        "their_latest": {"type": "string"}, "last_move": {"type": "string"},
        "action": {"type": "string", "enum": ["clarify", "deepen", "answer", "add_value", "next_step", "listen"]},
        "card_on_screen": {"type": "string", "enum": ["no_card", "keep", "update", "replace", "invalid", "withdraw"]},
        "because": {"type": "string"},
        "decision": {"type": "string", "enum": ["card", "silence"]},
        "line": {"type": "string"}, "source": {"type": "string"}, "source_quote": {"type": "string"},
    },
}

# The lines of Vocify's cold-call playbook that pushed scripted or presupposing cards, as approved on 2026-10-28.
REWORDED = {
    "Sí, te lo mando sin problema. Aunque entre tú y yo, sabemos que muchos de esos mails acaban en el agujero negro. Y entre "
    "correos de aquí para allá a veces perdemos más tiempo que sentándonos 15 minutos. Así te lo enseño funcionando y decides "
    "si tiene sentido. ¿Cuándo tienes un hueco?":
        "Sí, te lo mando hoy. Si ya ha dicho cuándo hablar, confírmalo tal cual. Si no hay nada fijado y hay interés, propón "
        "concretar un momento corto para verlo juntos, porque por correo se suele quedar en el aire: «¿Lo vemos 15 minutos "
        "cuando lo hayas leído? ¿Qué día te viene bien?»",
    "Entiendo. ¿Y durante la reunión el comercial recibe sugerencias automáticamente según lo que está diciendo el cliente, o "
    "tiene que entrar a consultar la herramienta?":
        "Entiendo. Primero entiende qué hace esa herramienta en la práctica y qué les da («¿Y para qué la usáis sobre todo?»). "
        "Pregunta por lo que pasa durante la reunión solo si aún no lo ha contado.",
    "Eso está genial. Al final, cuanto mejor está el playbook, más valor tiene que los comerciales puedan utilizarlo bien. "
    "¿Cómo conseguís que lo tengan presente cuando aparecen situaciones inesperadas durante las reuniones? Una pregunta más, "
    "sin discutirle; si sigue sin haber nada, cambia de rama en vez de insistir.":
        "Eso está genial. Entiende cómo trabajan hoy y qué les ha dado («¿Qué es lo que mejor os está funcionando?»), sin "
        "discutirle. Sigue explorando mientras aporte y esté receptivo; si no aparece nada, cambia de rama en vez de insistir.",
    "Perfecto. ¿Y cómo lo trabajáis normalmente, revisando llamadas después o de alguna otra manera? Claro, eso ayuda mucho "
    "para la siguiente reunión. Lo que estamos buscando con Vocify es que el comercial también tenga apoyo durante la "
    "conversación.":
        "Perfecto. ¿Y cómo lo trabajáis normalmente, revisando llamadas después o de alguna otra manera? Presenta el apoyo de "
        "Vocify durante la conversación solo cuando hayan contado algo que se les escapa en el momento.",
    "Seguro que tenéis capacidad. ¿Es algo que ya habéis construido o que estáis valorando desarrollar? Porque una cosa es "
    "hacer MVPs y la otra distinta es poder mantener algo y afinar con miles de conversaciones.":
        "Seguro que tenéis capacidad. ¿Es algo que ya habéis construido o que estáis valorando desarrollar? Solo si lo están "
        "valorando: una cosa es hacer MVPs y la otra distinta es poder mantener algo y afinar con miles de conversaciones.",
    "Lanza una pregunta abierta y deja hablar al prospecto sin interrumpir ni volver al pitch. Example: «¿Cuántos comerciales "
    "tenéis haciendo reuniones actualmente?»":
        "Lanza una pregunta abierta y deja hablar al prospecto sin interrumpir ni volver al pitch.",
    "Pregunta por el número de comerciales, el dolor real en las reuniones o el CRM que utilizan, y el prospecto responde al "
    "menos a uno de los tres.":
        "Saber el tamaño del equipo, el dolor real en las reuniones y el CRM cuando ayude a decidir si hay encaje o a preparar "
        "la demo, no como lista.",
    "cuántas horas dedica a revisarlas o a acompañar y qué se queda sin revisar.": "cuántas horas dedica a revisarlas o a acompañar.",
}
LEVEL_NOTES = {
    "APPROVED ANSWERS (": "(Level 4: ways to answer. Their facts are a source; their tactic is only a suggestion.)",
    "STEPS (": "(Level 2: what the company wants each phase to achieve, not questions to ask in order.)",
    "WHAT TO FIND OUT (": "(Level 2: what is worth learning when it matters for a decision, not a list to ask.)",
}


# The examples the model kept copying where they did not fit: the situations' and the Problema step's.
STEP_EXAMPLES_OUT = (" Example: «¿Cómo lo tenéis organizado ahora?»",)
SITUATION_LABELS = ("When it applies:", "What to do:", "What not to do:")


def sources_for(context: str) -> str:
    """The context with the reworded playbook lines, without the examples of the situations and of the Problema step,
    and a note under each block saying its level. Block headers stay as they are: the fact check finds the sources by
    them."""
    # Published in Vocify's playbook on 2026-10-28: a context read after that has them already.
    for old, new in {**REWORDED, **{e: "" for e in STEP_EXAMPLES_OUT}}.items():
        context = context.replace(old, new)
    lines, example = [], False
    for line in context.splitlines():
        # A situation's example runs from "Example:" to its next field, the next situation or a blank line.
        if line.startswith("Example:"):
            example = True
            continue
        if example and (not line.strip() or line.startswith(SITUATION_LABELS) or line[:1].isdigit() or line.startswith("## ")):
            example = False
        if example:
            continue
        lines.append(line)
        lines += [note for header, note in LEVEL_NOTES.items() if line.startswith(header)]
    return "\n".join(lines)


FACT_SYSTEM = v2.FACT_SYSTEM.replace(
    "  · a proposal: a question or a suggestion of a next step («¿te llamo en enero?», «¿lo vemos el martes a las 10?»): it\n"
    "    states nothing, fine when it fits the conversation;\n",
    "  · a proposal: a question or a suggestion of a next step («¿te llamo en enero?», «¿lo vemos el martes a las 10?»): it\n"
    "    states nothing, fine when it fits the conversation; but it is unsupported when it goes against what the other side\n"
    "    set or said (a date earlier than the one they gave, another channel or person than the one they named, whether\n"
    "    their solution misses something they said it covers) or asks again what they already answered;\n", 1).replace(
    "Each kind of content has its own source:\n",
    "Each kind of content has its own source:\n"
    "- General knowledge that is not about the seller's company, product or offer nor about the other side (what a common\n"
    "  business term means, how something usually works in sales): fine when it is correct and commonly known.\n", 1)
assert "asks again what they already answered" in FACT_SYSTEM and "General knowledge" in FACT_SYSTEM


def fact_check(card: dict, cache_key: str, conversation: str) -> dict:
    """run_v2's fact check, with general knowledge allowed («¿qué es un SDR?» got no answer: it was not in the SOURCES)."""
    source = card.get("authorized") or card.get("source_quote") or "(none: this line has no approved source)"
    stated = " ".join(v2.asserted(card["say"]).split()).strip(" .:;,")
    user = (f"SOURCE: «{source}»\nTHE CONVERSATION (latest last):\n{conversation or '-'}\nTHE LINE: «{card['say']}»\n"
            f"WHAT THE LINE STATES OUTSIDE ITS QUESTIONS: «{stated or '(nothing: only questions)'}»"
            + (f"\nWHAT ITS QUESTIONS OFFER TO SHOW THE PRODUCT DOING (a claim, judged like a statement): «{v2.offered(card['say'])}»"
               if v2.offered(card["say"]) else ""))
    return v2.ask(FACT_SYSTEM, user, v2.FACT_EFFORT, 700, v2.FACT_SCHEMA, f"{cache_key}-facts", temperature=0.0)


def turn_checks(call: dict, custom: dict | None, cache: Path) -> dict[str, dict]:
    """The turn check asked again with the two fixes, kept apart from production's cached answers."""
    path = cache / f"{call['id']}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    from app.services.copilot import turn

    kinds = dict(turn.OBJECTIONS)
    asked = turn.questions_for
    turn.OBJECTIONS["none"] = kinds["none"] + (" Not recognising who is calling or what it is about («no te ubico», «no caigo», "
                                               "«¿de qué?») is none.")
    turn.OBJECTIONS["timing"] = kinds["timing"] + " Not recognising the caller is not timing."

    def own(custom_entries):
        q = asked(custom_entries)
        crit = {k: (v.replace("The team's own objection", "Only when they say this or the same thing in other words, not "
                              "something related to it: the team's own objection") if k.startswith("objection:custom:") else v)
                for k, v in q["objection"]["criteria"].items()}
        return {**q, "objection": {**q["objection"], "criteria": crit}}

    turn.questions_for = own
    try:
        turns = call["turns"]
        signals = semantic.listening(turns)
        asks = [i for i, t in enumerate(turns) if t["who"] == "them" and i not in signals and len(semantic.tokens(t["text"])) >= 2]

        async def one(i):
            convo = "\n".join(f"{'Them' if u['who'] == 'them' else 'You'}: {u['text']}" for u in turns[max(0, i - semantic.CONVERSATION_TURNS):i + 1])
            r = await turn.read_turn(convo, turns[i]["text"], custom)
            if r["finished"] is None and r["objection"] is None:
                raise RuntimeError(f"turn check unavailable for {call['id']} {turns[i]['id']}: nothing is kept")
            return turns[i]["id"], {"finished": r["finished"] is not False, "objection": r.get("entry_id") or r["objection"] or "none"}

        async def run():
            return dict(await asyncio.gather(*(one(i) for i in asks)))

        out = asyncio.run(run())
    finally:
        turn.OBJECTIONS.clear()
        turn.OBJECTIONS.update(kinds)
        turn.questions_for = asked
    cache.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


MIN_READ_S = 4.0  # a card on screen is not changed before the rep could read it


def live(shown: list[dict]) -> dict | None:
    """The card on screen: the last one shown, unless it was withdrawn or replaced."""
    return shown[-1] if shown and not shown[-1].get("withdrawn_t") and not shown[-1].get("replaced_t") else None


def reading_input(sources, turns, upto, end, now, shown, on_screen: dict | None) -> str:
    log = v2.log_text(turns, upto, [], v2.on_screen(shown, [], now), end)
    screen = (f"CARD ON SCREEN NOW (the rep has not used it yet): «{on_screen['say']}», shown at "
              f"{int(on_screen['visible_t'] // 60)}:{int(on_screen['visible_t'] % 60):02d}") if on_screen else "CARD ON SCREEN NOW: none"
    return (f"{sources}\n\n{calendar(sources)}\n\nLOG (\"You\" is the rep; [card shown] is a card the rep saw):\n{log}\n\n"
            f"{v2.speaking_now_lines(turns, end, now)}\n\n{thread(turns, end, shown, now)}\n\n{screen}\n\nNOW: {round(now)} s into the call.")


def play(call: dict, sources: str, checks: dict[str, dict]) -> dict:
    """turns-6b's clock and protections with the engine's reading and the card's life on screen."""
    turns = v2.chunked(call["turns"])
    end = ends(turns)
    todo = rt.moments(turns, checks)
    key = f"engine-{call['id']}"
    readings, shown, dropped = [], [], []
    clock, spent = 0.0, 0.0
    signals = semantic.listening(turns)
    them_floors = [(turns[f["first"]]["t"], end[max(i for i in range(f["first"], f["last"] + 1) if i not in signals)])
                   for f in semantic.floors(turns) if f["who"] == "them"]

    def vet(out: dict, start: float, at: float, upto: int, against: list[dict]):
        cost = 0.0
        source = out["source"].strip() or "context"
        if source == "context":
            out["source_quote"] = ""
        card = {"act": "answer" if source != "context" else "move", "say": out["line"].strip(), "source": source,
                "source_quote": out["source_quote"], "evidence": [turns[upto - 1]["id"]], "objective": "", "born_t": start,
                "help": "answer" if source != "context" else "opportunity", "out": out}
        if card["act"] == "answer" and not v2.authorized_text(sources, card):
            card.update(act="move", help="opportunity")
        why = v2.basic_checks(card, [], turns, upto, against, [], sources)
        if why:
            return card, why, at, cost
        conv = v2.conversation_lines(turns, end, at, n=v2.FACT_TURNS, chars=v2.FACT_CHARS)
        with ThreadPoolExecutor(max_workers=3) as pool:
            f = pool.submit(fact_check, card, key, conv)
            c = pool.submit(v2.closing_check, v2.conversation_lines(turns, end, at, n=v2.CLOSING_TURNS), key)
            r = pool.submit(rt.repeat_check, card["say"], against, turns, end, at, key) if against else None
            facts, closing = f.result(), c.result()
            rep = r.result() if r else {"parsed": {"repeats": False, "same_as": ""}, "latency": 0.0, "cost": 0.0}
        cost += facts["cost"] + closing["cost"] + rep["cost"]
        at += min(max(facts["latency"], closing["latency"], rep["latency"]), v2.CLOCK_LATENCY_CAP_S)
        if (facts["parsed"] or {"unsupported": True})["unsupported"]:
            return card, "unsupported_fact", at, cost
        if v2.closing_confirmed(closing["parsed"], turns, end, at):
            return card, "call_closing", at, cost
        if v2.call_over(at, end[-1]):
            return card, "call_over", at, cost
        if v2.after_goodbye(turns, end, at):
            return card, "after_goodbye", at, cost
        if (rep["parsed"] or {}).get("repeats"):
            card["same_as"] = rep["parsed"].get("same_as", "")
            return card, "repeats", at, cost
        return card, None, at, cost

    while todo:
        start = todo[0][0] if todo[0][1] == "them_urgent" else max(clock, todo[0][0])
        due = [r for t, r in todo if t <= start]
        todo = [(t, r) for t, r in todo if t > start]
        reason = next((r for r in ("them_urgent", "them_end", "them_mid", "rep_long") if r in due), due[0])
        upto = finished_by(end, start)
        current = live(shown)
        pending = current if current and not rt.rep_could_use(shown, turns, end, them_floors, start) else None
        res = v2.ask(SYSTEM, reading_input(sources, turns, upto, end, start, shown, pending), "none", rt.TOKENS + 250, SCHEMA, key)
        spent += res["cost"]
        at = start + min(res["latency"], v2.CLOCK_LATENCY_CAP_S)
        clock = max(clock, at)
        out = res["parsed"]
        entry = {"start_t": start, "reason": reason, "after_turn": turns[upto - 1]["id"], "error": res["error"], "output": out,
                 "on_screen": pending["say"] if pending else None, "cost": res["cost"], "event": ""}
        readings.append(entry)
        if not out:
            continue
        status = out["card_on_screen"] if pending else "no_card"
        if pending and status == "no_card":  # a card on screen it did not account for: a new line replaces it
            status = "replace"
        if pending and status in ("invalid", "withdraw"):
            # Wrong now: off at once. Only no longer the best: not before the rep could read it.
            if status == "withdraw" and at - pending["visible_t"] < MIN_READ_S:
                entry["event"] = "keep:card_on_screen_too_new"
                continue
            pending["withdrawn_t"] = round(at, 1)
            entry["event"] = "invalid" if status == "invalid" else "withdraw"
            continue
        if out["decision"] != "card" or not out["line"].strip() or (pending and status == "keep"):
            entry["event"] = "keep" if pending and status == "keep" else "silence"
            continue
        if out["understanding_confidence"] == "low":
            entry["event"] = "low_confidence"
            continue
        change = pending is not None
        # Every card rests on their words: copied from what they said, or it is not shown.
        said = " ".join(t["text"] for t in turns[:upto] if t["who"] == "them")
        if len(out["because"].split()) < 3 or not quote_in(out["because"], said):
            entry["event"] = "drop:no_reason_in_their_words"
            dropped.append({"say": out["line"], "why": entry["event"]})
            continue
        if change:
            # A change: never once the rep has started to speak, nor before the card on screen could be read.
            if gate.rep_said(turns, pending["visible_t"], at) >= 3:
                entry["event"] = "drop:rep_started_speaking"
                dropped.append({"say": out["line"], "why": entry["event"]})
                continue
            if at - pending["visible_t"] < MIN_READ_S:
                entry["event"] = "drop:card_on_screen_too_new"
                dropped.append({"say": out["line"], "why": entry["event"]})
                continue
        # An update keeps the intention of the card on screen: it is not checked as a repeat of it.
        against = [s for s in shown if s is not pending] if change and status == "update" else shown
        card, why, at, extra = vet(out, start, at, upto, against)
        spent += extra
        if why:
            entry["event"] = f"drop:{why}"
            dropped.append({**card, "why": why})
            continue
        if change:
            pending["replaced_t"] = round(at, 1)
        done = finished_by(end, at)
        shown.append({"visible_t": round(at, 1), "after_turn": turns[max(0, done - 1)]["id"], "say": card["say"], "source": card["source"],
                      "born_t": start, "reason": reason, "action": out["action"], "change": status if change else "new",
                      "what_is_happening": out["what_is_happening"], "observed": out["observed"], "hypotheses": out["hypotheses"],
                      "unknown": out["unknown"], "situation": out["situation"]})
        entry["event"] = {"update": "update", "replace": "replace"}.get(status, "shown") if change else "shown"
    return {"id": call["id"], "readings": readings, "shown": shown, "dropped": dropped, "duration": end[-1], "cost": spent}
