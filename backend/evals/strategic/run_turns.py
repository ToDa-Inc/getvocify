"""The brain as a voice agent that may stay silent: it listens, and at the end of what the other side says it decides
between one card and silence.

    cd backend && .venv/bin/python -m evals.strategic.run_turns --only 98d65a63,bad69309 --out turns.json

- WHEN it reads (code, with the turn check production already runs: Jev): when the other side ends their intervention
  (the last turn of their floor, listening signals of the rep inside it); at once when the turn check flags a question
  or an objection (the urgent path); once when the rep has held the floor REP_FLOOR_S seconds (a long pitch). Not at
  every pause: a reading on half an idea is answered by what they say next.
- WHAT it says (DeepSeek, one call): a short policy, the playbook and the conversation. It returns a card or silence.
- PROTECTIONS (code, as before): the fact check, the end of the call, their goodbye, the same text twice, a second card
  before the rep could use the first.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evals.strategic import gate  # noqa: E402
from evals.strategic.forma_de_trabajar import VARIANTS, with_variant  # noqa: E402
from evals.strategic import run_v2 as v2  # noqa: E402
from evals.strategic import turns as semantic  # noqa: E402
from evals.strategic.run import CALLS, context_for, ends, finished_by  # noqa: E402
from evals.strategic.run_min import calendar, thread  # noqa: E402

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
# The small gate's question about repetition: asked apart, with little context, because the model writing the card does
# not see its own repeats (four ways of saying it in the prompt left them at three quarters of the bad cards).
REPEAT_SYSTEM = """A live assistant wants to show a salesperson ONE new card. The cards already shown in this call are
listed, then what was said since the last one. Is the new card the same move as a card already shown (the same request,
proposal or question, even in other words) while the other side has not answered that card with anything new? A move
adapted to something new they said (a new constraint, a new person, an answer, a new topic) is not a repeat. Answer JSON
{"repeats": true|false, "same_as": "the earlier card it repeats, or empty", "why": "at most 10 words"}."""
REPEAT_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["repeats", "same_as", "why"],
                 "properties": {"repeats": {"type": "boolean"}, "same_as": {"type": "string"}, "why": {"type": "string"}}}
MIN_SHOW_S = 6.0  # a card on screen does not change for this long, and never once the rep has started to speak
# The reading is still asked for at most 20 words; only a clearly excessive card is refused (half the cards cut at 25 words
# were good: one of them, on a prospect's goal and numbers, had 31 words).
v2.MAX_CARD_WORDS = 35
TOKENS = 450
MIN_SUBSTANCE = 4  # an intervention with fewer words of substance («sí, claro, dime») is not read
# A long intervention is also read while it goes on (in one call the prospect spoke from 2:36 to 5:56 and the main pain, at 2:44, waited
# three minutes): at a pause where the turn check says an idea is complete and MID_WORDS words of substance came since the
# last reading, or every MID_GAP_S seconds as a backstop. «Sí», «claro» from the rep still do not end their turn.
MID_WORDS, MID_GAP_S = 25, 40.0
REP_FLOOR_S = 45.0


def moments(turns: list[dict], checks: dict[str, dict]) -> list[tuple[float, str]]:
    """(second, reason): "them_end" at the end of each intervention of the other side with substance, "them_urgent" at
    the end of a turn the turn check flags as a question or an objection, "rep_long" once REP_FLOOR_S into a rep floor."""
    end = ends(turns)
    signals = semantic.listening(turns)
    out = []
    for f in semantic.floors(turns):
        mine = [i for i in range(f["first"], f["last"] + 1) if i not in signals and turns[i]["who"] == f["who"]]
        if not mine:
            continue
        if f["who"] == "them":
            # The turn check flags the same objection on each piece of one intervention («mándamelo por correo» three
            # times in Samuel's): it is read once, at its first piece, and again only for a different one.
            urgent, kinds = [], set()
            for i in mine:
                kind = (checks.get(turns[i]["id"]) or {}).get("objection", "none")
                kind = (checks.get(turns[i]["id"]) or {}).get("entry_id") or kind
                # Only once the turn check says the idea is complete (unknown counts as complete): a card on «¿Se
                # podría…» answered half a question.
                if kind not in ("none", None) and kind not in kinds and (checks.get(turns[i]["id"]) or {}).get("finished") is not False:
                    urgent.append(i)
                    kinds.add(kind)
            out += [(end[i], "them_urgent") for i in urgent if i != mine[-1]]
            last, said = turns[mine[0]]["t"], 0
            for i in mine[:-1]:
                said += semantic.substance(turns[i]["text"])
                if i in urgent:
                    last, said = end[i], 0
                    continue
                complete = (checks.get(turns[i]["id"]) or {}).get("finished") is True
                if (complete and said >= MID_WORDS) or (end[i] - last >= MID_GAP_S and said >= MIN_SUBSTANCE * 2):
                    out.append((end[i], "them_mid"))
                    last, said = end[i], 0
            if sum(semantic.substance(turns[i]["text"]) for i in mine) >= MIN_SUBSTANCE:
                out.append((end[mine[-1]], "them_urgent" if mine[-1] in urgent else "them_end"))
        elif end[mine[-1]] - turns[mine[0]]["t"] >= REP_FLOOR_S:
            out.append((turns[mine[0]]["t"] + REP_FLOOR_S, "rep_long"))
    return sorted(out)


def rep_could_use(shown: list[dict], turns: list[dict], end: list[float], them_floors: list[tuple[float, float]], at: float) -> bool:
    """The rep has had the chance to use the card on screen: they said REP_WORDS words of substance since it appeared,
    or the other side began and finished a new intervention after it. The other side still talking is not that chance
    (three cards came in 15 s while Ribesalat's prospect went on about the 10th of November)."""
    if not shown:
        return True
    last = shown[-1]["visible_t"]
    return gate.rep_said(turns, last, at) >= v2.REP_WORDS or any(last < a and b <= at for a, b in them_floors)


def repeat_check(say: str, shown: list[dict], turns: list[dict], end: list[float], at: float, key: str) -> dict:
    cards = "\n".join(f"- {int(s['visible_t'] // 60)}:{int(s['visible_t'] % 60):02d} «{s['say']}»" for s in shown)
    since = v2.conversation_lines(turns, end, at, since=shown[-1]["visible_t"]) if shown else ""
    user = f"CARDS ALREADY SHOWN:\n{cards}\nSAID SINCE THE LAST CARD:\n{since or '(nothing)'}\nTHE NEW CARD: «{say}»"
    return v2.ask(REPEAT_SYSTEM, user, "none", 120, REPEAT_SCHEMA, f"{key}-repeat", temperature=0.0)


def can_update(shown: list[dict], turns: list[dict], them_floors: list[tuple[float, float]], reason: str, at: float) -> bool:
    """The card on screen may be replaced only when it came during the intervention that just ended, the rep has not
    started to speak since, and it has been up MIN_SHOW_S: what they added after it changed the move."""
    if not shown or reason not in ("them_end", "them_urgent"):
        return False
    last = shown[-1]["visible_t"]
    during = any(a <= last <= b + 0.5 and b <= at for a, b in them_floors)
    return during and at - last >= MIN_SHOW_S and gate.rep_said(turns, last, at) < 3


def reading_input(sources, turns, upto, end, now, shown, rules: str = "") -> str:
    log = v2.log_text(turns, upto, [], v2.on_screen(shown, [], now), end)
    return (f"{sources}\n\n{calendar(sources)}\n\nLOG (\"You\" is the rep; [card shown] is a card the rep saw):\n{log}\n\n"
            f"{v2.speaking_now_lines(turns, end, now)}\n\n{thread(turns, end, shown, now)}\n\n{rules + chr(10) * 2 if rules else ''}"
            f"NOW: {round(now)} s into the call.")


# The company's own rules (the playbook's «Reglas»): read last, right before NOW, and above everything else. Measured
# 2026-10-27: inside the playbook block a rule lost to the approved answer of the same objection (CRM renewal 1/4).
RULES_NOTE = """

COMPANY RULES (when the input has them, right before NOW): they are the company's own way of working and come before
everything above, the approved answers and the goal included. When a rule fits this moment, the card does what it says
(an approved answer may still give the facts); a rule about how to talk applies to every card. They are never a source
of facts."""


def rules_block(rules: list[str]) -> str:
    return "COMPANY RULES:\n" + "\n".join(f"- {r}" for r in rules) if rules else ""


def moment_schema(ids: list[str]) -> dict:
    """The reading's answer with the moment it recognised (forma_de_trabajar.with_moments)."""
    props = dict(SCHEMA["properties"])
    order = ["what_is_happening", "understanding_confidence", "their_latest", "last_move"]
    return {**SCHEMA, "required": [*order, "moment", *[k for k in SCHEMA["required"] if k not in order]],
            "properties": {**{k: props.pop(k) for k in order}, "moment": {"type": "string", "enum": [*ids, "none"]}, **props}}


def play(call: dict, sources: str, custom: dict | None, schema: dict = SCHEMA, rules: list[str] | None = None) -> dict:
    turns = v2.chunked(call["turns"])
    end = ends(turns)
    checks = semantic.turn_readings(call, custom)
    todo = moments(turns, checks)
    key = f"brain-turns-{call['id']}"
    system = SYSTEM + RULES_NOTE if rules else SYSTEM
    tail = rules_block(rules or [])
    readings, shown, dropped = [], [], []
    clock, spent = 0.0, 0.0

    def vet(out: dict, start: float, at: float, upto: int, reason: str):
        """The card the reading wrote, through the protections: (card, why or None, when it would show, cost)."""
        cost = 0.0
        source = out["source"].strip() or "context"
        if source == "context":
            out["source_quote"] = ""  # a line resting on the conversation has no approved text to quote (the model quoted the call)
        card = {"act": "answer" if source != "context" else "move", "say": out["line"].strip(), "source": source,
                "source_quote": out["source_quote"], "evidence": [turns[upto - 1]["id"]], "objective": "", "born_t": start,
                "help": "answer" if source != "context" else "opportunity", "out": out}
        if card["act"] == "answer" and not v2.authorized_text(sources, card):
            card.update(act="move", help="opportunity")
        why = v2.basic_checks(card, [], turns, upto, shown, [], sources)
        if why:
            return card, why, at, cost
        conv = v2.conversation_lines(turns, end, at, n=v2.FACT_TURNS, chars=v2.FACT_CHARS)
        with ThreadPoolExecutor(max_workers=3) as pool:  # the small gate: facts, the end of the call, repetition
            f = pool.submit(v2.fact_check, card, key, conv)
            c = pool.submit(v2.closing_check, v2.conversation_lines(turns, end, at, n=v2.CLOSING_TURNS), key)
            r = pool.submit(repeat_check, card["say"], shown, turns, end, at, key) if shown else None
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

    signals = semantic.listening(turns)
    them_floors = [(turns[f["first"]]["t"], end[max(i for i in range(f["first"], f["last"] + 1) if i not in signals)])
                   for f in semantic.floors(turns) if f["who"] == "them"]

    while todo:
        start = todo[0][0] if todo[0][1] == "them_urgent" else max(clock, todo[0][0])
        due = [r for t, r in todo if t <= start]
        todo = [(t, r) for t, r in todo if t > start]
        reason = next((r for r in ("them_urgent", "them_end", "them_mid", "rep_long") if r in due), due[0])
        upto = finished_by(end, start)
        res = v2.ask(system, reading_input(sources, turns, upto, end, start, shown, tail), "none", TOKENS, schema, key)
        spent += res["cost"]
        at = start + min(res["latency"], v2.CLOCK_LATENCY_CAP_S)
        clock = max(clock, at)
        out = res["parsed"]
        entry = {"start_t": start, "reason": reason, "after_turn": turns[upto - 1]["id"], "error": res["error"], "output": out,
                 **{k: res[k] for k in ("latency", "prompt_tokens", "cached_tokens", "completion_tokens", "cost")}, "event": ""}
        readings.append(entry)
        if not out:
            continue
        if out["decision"] != "card" or not out["line"].strip():
            entry["event"] = "silence"
            continue
        if out["understanding_confidence"] == "low":  # not sure what was meant (garbled, ambiguous, irony): no card
            entry["event"] = "low_confidence"
            continue
        card, why, at, extra = vet(out, start, at, upto, reason)
        spent += extra
        if why == "repeats":  # the small gate saw the same move: one more try for a different one, or silence
            entry["repeat_of"] = card.get("same_as", "")
            res2 = v2.ask(system, reading_input(sources, turns, upto, end, start, shown, tail) + f"\n\nYOUR CARD «{card['say']}» REPEATS «{card.get('same_as', '')}», "
                          "already shown, with nothing new from them since. Give a different next move that responds to what they "
                          "said, or silence.", "none", TOKENS, schema, key)
            spent += res2["cost"]
            at += min(res2["latency"], v2.CLOCK_LATENCY_CAP_S)
            out = res2["parsed"]
            if not out or out["decision"] != "card" or not out["line"].strip() or out["understanding_confidence"] == "low":
                entry["event"] = "drop:repeats→silence"
                dropped.append({**card, "why": "repeats"})
                continue
            card, why, at, extra = vet(out, start, at, upto, reason)
            spent += extra
        if why:
            entry["event"] = f"drop:{why}"
            dropped.append({**card, "why": why})
            continue
        if not rep_could_use(shown, turns, end, them_floors, at):
            if can_update(shown, turns, them_floors, reason, at):
                shown[-1]["replaced_t"] = round(at, 1)
                card["updates"] = True
            else:
                entry["event"] = "drop:rep_has_last_card"
                dropped.append({**card, "why": "rep_has_last_card"})
                continue
        done = finished_by(end, at)
        shown.append({"visible_t": round(at, 1), "after_turn": turns[max(0, done - 1)]["id"], "kind": card["act"], "say": card["say"],
                      "source": card["source"], "source_quote": card["source_quote"], "born_t": start, "reason": reason,
                      "what_is_happening": out["what_is_happening"], "confidence": out["understanding_confidence"],
                      "their_latest": out["their_latest"], "last_move": out["last_move"], "moment": out.get("moment"), "updates": card.get("updates", False), "playbook_example": v2.playbook_example(sources, card),
                      "reaction_s": round(at - max((end[i] for i, t in enumerate(turns) if t["who"] == "them" and end[i] <= start + 1e-6), default=start), 1)})
        entry["event"] = "shown"
    return {"id": call["id"], "mode": "turns", "readings": readings, "shown": shown, "notes": [], "dropped": dropped,
            "duration": end[-1], "cost": spent}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--only", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--variant", choices=VARIANTS, default="base", help="the playbook's goal and criteria (forma_de_trabajar)")
    args = parser.parse_args()
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    from evals.copilot.run import load_production_provider

    load_production_provider()
    from app.services.copilot.playbook_objections import custom_entries
    from app.services.playbooks.live import live_snapshot
    from evals.copilot.export_calls import supabase

    calls = [json.loads((CALLS / f"{c}.local.json").read_text(encoding="utf-8")) for c in args.only.split(",")]
    contexts = [with_variant(context_for({**c, "playbook_version_id": None}).replace("GOAL:", "USUAL GOAL FOR THIS TYPE OF CALL (a starting point, not an obligation):", 1),
                             args.variant) for c in calls]
    custom = custom_entries(live_snapshot(supabase(), calls[0]["company_id"], calls[0]["motion"]))
    for c in calls:
        semantic.turn_readings(c, custom)
    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        played = list(pool.map(lambda pair: play(pair[0], pair[1], custom), zip(calls, contexts)))
    Path(args.out).write_text(json.dumps({"mode": "turns", "version": "turns-6b", "variant": args.variant, "model": v2.MODEL, "played": played},
                                         ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    for p in played:
        lat = sorted(r["latency"] for r in p["readings"] if not r["error"])
        silent = sum(r["event"] == "silence" for r in p["readings"])
        print(f"{p['id']}: {len(p['readings'])} readings ({silent} silence); shown {len(p['shown'])}; "
              f"latency p50 {lat[len(lat) // 2]:.1f} s p90 {lat[int(len(lat) * 0.9)]:.1f} s; ${p['cost']:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
