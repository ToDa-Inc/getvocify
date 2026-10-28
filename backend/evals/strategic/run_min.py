"""The minimal brain: one question per reading, the code keeps everything else.

    cd backend && .venv/bin/python -m evals.strategic.run_min --only 0c439183 --out min.json

Responsibilities, kept apart:
- The code decides WHEN to read (turns.py, as in run_v2), keeps the memory (the conversation, the cards the rep saw, the
  commercial progress) and protects (the fact check, the end of the call, the other side's goodbye, the same card twice,
  a second move before the rep could use the first). These are not in the prompt.
- The model answers one question: what is the next useful intervention now, if any. It writes its understanding, the
  priority, the line, and the checks it answered before deciding to show it. No queue of pending cards and no second
  model judging the card again: each reading decides from scratch.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evals.strategic import gate  # noqa: E402
from evals.strategic import run_v2 as v2  # noqa: E402
from evals.strategic import turns as semantic  # noqa: E402
from evals.strategic.run import CALLS, context_for, ends, finished_by  # noqa: E402

SYSTEM = """You are Vocify, the live sales copilot of a salesperson ("the rep", "You") in a call with a prospect ("Them").
Your one job: help the rep carry out THEIR COMPANY's sales strategy by choosing the next useful intervention with what
is known now. If no intervention adds enough value, show nothing. Final priority: maximum incremental commercial value
with minimum distraction.

INCREMENTAL MEANS NEW TO THIS CONVERSATION. Every card is a move. The moves in CARDS SHOWN, and what the rep has already
said, are made. When the other side answers a move, even by repeating their request (asking again for the email after
the rep proposed 15 minutes), their answer is the new information: the next card responds to THAT with the next step
for that situation (the PLAYBOOK's when it has one: who else will see it and what they will judge it on, when to pick
it up again). Never the same move again, in the same or other words. If no further step adds enough, show nothing.

The PLAYBOOK is the company's strategy. Its goal and the OBJECTIVES of its steps say what to achieve; its rules are
mandatory; its tactics, examples and approved answers say how the company likes to do it: adapt them to this
conversation, never recite them, never replace them with a method of your own.

Each time, in this order:
1. Understand. What did they just say? Separate facts about THEIR situation from examples, hypotheses or mere interest.
   What is the rep doing right now? In "progress", list each objective that moved now: the evidence (verbatim words of
   either side), your interpretation, and its state ("advancing": evidence toward it, not enough; "met": its "met when"
   is fully true; "blocked": they stopped it for now; "reopened"). Usually nothing moved: [].
2. Priority. What is new rules: when they just asked something, objected, insisted, or set a limit (no time, email
   instead, not this year, a day that does not work), the next help answers THAT, with the approved answer for it when
   there is one. Otherwise, the objective the conversation gives a concrete opening for now: a meeting they open comes
   first; then a need not yet confirmed, in the PLAYBOOK's order by default. Never an objective already met, never a
   branch they ruled out without new evidence.
3. Next move. First write "last_move": the last move already made about what is on the table now (a card in THE
   THREAD, or the rep's own words; "" when none), and "their_answer": what they said to it since ("" when nothing
   yet). Then the line: it responds to their_answer and never makes last_move again. The line the rep can say as is: a
   question or a proposal built from their words, at most 20 words. Or a very short instruction when the rep's own
   behaviour is the problem (at most 8 words, respectful).
4. Worth showing? Answer each check honestly, then decide "show":
   - relevant_now: it answers what is on the table at this instant.
   - adds_value: it moves the company's strategy forward beyond what the rep is doing.
   - rep_already_doing_it: the rep has said or is saying this same move (never wait to see whether the rep will do it).
   - repeats: it makes a move already made (the same proposal or question, in any words) without responding to what
     they said since.
   - respects_limits: it respects what they asked to be respected and the PLAYBOOK's rules.
   "show" is true only when relevant_now and adds_value are true and the other three say it is fine.

Facts: a fact about the product, prices, customers, results or guarantees only when it restates the SOURCES ("source":
the entry id as written before " · ", "offer" or "knowledge"; "source_quote": the verbatim text it rests on).
Otherwise "source" is "context" and the line states no such fact. A proposal (a question, a day) states nothing; never
present it as already agreed, never name a person or a date they did not mention. For days, use the CALENDAR: never
work out a weekday yourself. Write the line in the language of the call; everything else in English, briefly."""

SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["progress", "situation", "priority", "last_move", "their_answer", "line", "source", "source_quote", "objective", "checks", "show"],
    "properties": {
        "progress": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                     "required": ["id", "state", "interpretation", "quote"],
                     "properties": {"id": {"type": "string"}, "state": {"type": "string", "enum": list(v2.PROGRESS_STATES)},
                                    "interpretation": {"type": "string"}, "quote": {"type": "string"}}}},
        "situation": {"type": "string"}, "priority": {"type": "string"},
        "last_move": {"type": "string"}, "their_answer": {"type": "string"},
        "line": {"type": "string"}, "source": {"type": "string"}, "source_quote": {"type": "string"}, "objective": {"type": "string"},
        "checks": {"type": "object", "additionalProperties": False,
                   "required": ["relevant_now", "adds_value", "rep_already_doing_it", "repeats", "respects_limits"],
                   "properties": {k: {"type": "boolean"} for k in ("relevant_now", "adds_value", "rep_already_doing_it", "repeats", "respects_limits")}},
        "show": {"type": "boolean"},
    },
}
TOKENS = 600
DAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def calendar(sources: str, days: int = 28) -> str:
    """The next weeks with their weekdays, written by the code (3.7 called 11 November a Tuesday)."""
    m = re.search(r"TODAY: \w+ (\d{4})-(\d{2})-(\d{2})", sources)
    if not m:
        return ""
    today = date(int(m[1]), int(m[2]), int(m[3]))
    return "CALENDAR: " + ", ".join(f"{DAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]}" + (" (hoy)" if d == today else "")
                                    for d in (today + timedelta(k) for k in range(days)))


def objectives_list(intent: dict) -> str:
    rows = [f"- goal → {intent['goal']['objective']} · met when: {intent['goal']['met_when']}"]
    rows += [f"- {s['id']} → {s['objective']} · met when: {s['met_when']}" for s in intent["steps"] if s["kind"] == "objective"]
    rows += [f"- {d['id']} → {d['objective']} · met when: {d['met_when']}" for d in intent["data"]]
    return "OBJECTIVES (what each step and data point is for):\n" + "\n".join(rows)


THREAD_CARDS, THREAD_WORDS = 3, 45


def thread(turns: list[dict], end: list[float], shown: list[dict], now: float) -> str:
    """The latest cards and what each side said after each one, up to the next card or now: the moves already made and
    their answers, so the next card is compared with them before it is written (3.7 asked three times who decides)."""
    out = []
    recent = [s for s in shown if s["visible_t"] <= now][-THREAD_CARDS:]
    for k, s in enumerate(recent):
        until = recent[k + 1]["visible_t"] if k + 1 < len(recent) else now
        said = {"you": [], "them": []}
        for i, t in enumerate(turns):
            if s["visible_t"] < end[i] and t["t"] <= until:
                said[t["who"]] += t["text"].split()
        them = " ".join(said["them"][-THREAD_WORDS:]) or "(nothing yet)"
        you = " ".join(said["you"][-THREAD_WORDS:]) or "(nothing yet)"
        out.append(f"- {int(s['visible_t'] // 60)}:{int(s['visible_t'] % 60):02d} card «{s['say']}»\n    then the rep: {you}\n    then they: {them}")
    return "THE THREAD (the latest moves already made and what came after each):\n" + ("\n".join(out) or "(no card yet)")


def reading_input(sources, intent, turns, upto, notes, end, now, shown) -> str:
    # Stable first (sources, objectives, calendar, the log that only grows), what changes each reading last.
    log = v2.log_text(turns, upto, notes, v2.on_screen(shown, [], now), end)
    cards = "\n".join(f"- {int(s['visible_t'] // 60)}:{int(s['visible_t'] % 60):02d} «{s['say']}»" for s in shown) or "(none)"
    return (f"{sources}\n\n{objectives_list(intent)}\n\n{calendar(sources)}\n\n"
            f"LOG (\"You\" is the rep; [card shown] is what the rep saw; progress notes are indented):\n{log}\n\n"
            f"{v2.speaking_now_lines(turns, end, now)}\n\nCARDS SHOWN SO FAR:\n{cards}\n"
            f"{v2.objectives_now(notes, intent)}\n\n{thread(turns, end, shown, now)}\n\nNOW: {round(now)} s into the call.")


def play(call: dict, sources: str, intent: dict, custom: dict | None) -> dict:
    turns = v2.chunked(call["turns"])
    end = ends(turns)
    moments = v2.read_moments(turns, semantic.turn_readings(call, custom))
    them_ideas = [t for t, r in moments if r.startswith("them")]
    key = f"brain-min-{call['id']}"
    notes, readings, shown, dropped = [], [], [], []
    clock, spent, last_read = 0.0, 0.0, -1e9

    def rep_could_use_last(at: float) -> bool:
        if not shown:
            return True
        last = shown[-1]["visible_t"]
        return any(last < t <= at for t in them_ideas) or gate.rep_said(turns, last, at) >= v2.REP_WORDS

    while moments:
        start = moments[0][0] if moments[0][1] == "them_urgent" else max(clock, moments[0][0])
        due = [r for t, r in moments if t <= start]
        moments = [(t, r) for t, r in moments if t > start]
        reason = "them" if any(r.startswith("them") for r in due) else "rep"
        if reason == "rep" and start - last_read < v2.REP_STRETCH_S:
            continue
        last_read = start
        upto = finished_by(end, start)
        res = v2.ask(SYSTEM, reading_input(sources, intent, turns, upto, notes, end, start, shown), "none", TOKENS, SCHEMA, key)
        spent += res["cost"]
        at = start + min(res["latency"], v2.CLOCK_LATENCY_CAP_S)
        clock = max(clock, at)
        out = res["parsed"]
        entry = {"start_t": start, "reason": reason, "after_turn": turns[upto - 1]["id"], "error": res["error"], "output": out,
                 **{k: res[k] for k in ("latency", "prompt_tokens", "cached_tokens", "completion_tokens", "cost")}, "event": ""}
        readings.append(entry)
        if not out:
            continue
        notes.extend(v2.keep_notes([{"type": "progress", "turn": "", "quote": p["quote"], "text": f"{p['id']} {p['state']}: {p['interpretation']}",
                                     "closes": ""} for p in out["progress"]], turns, upto, notes))
        if not (out["show"] and out["line"].strip()):
            entry["event"] = "silence" if not out["line"].strip() else "not_shown_by_checks"
            continue
        source = out["source"].strip() or "context"
        card = {"act": "answer" if source not in ("context",) else "move", "say": out["line"].strip(), "source": source,
                "source_quote": out["source_quote"], "evidence": [turns[upto - 1]["id"]], "objective": out["objective"],
                "born_t": start, "help": "answer" if source != "context" else "opportunity"}
        if card["act"] == "answer" and not v2.authorized_text(sources, card):
            card.update(act="move", help="opportunity")
        why = v2.basic_checks(card, notes, turns, upto, shown, [], sources)
        if not why:  # the fact check and the end of the call, side by side, on what had been said by then
            conv = v2.conversation_lines(turns, end, at, n=v2.FACT_TURNS, chars=v2.FACT_CHARS)
            with ThreadPoolExecutor(max_workers=2) as pool:
                f = pool.submit(v2.fact_check, card, key, conv)
                c = pool.submit(v2.closing_check, v2.conversation_lines(turns, end, at, n=v2.CLOSING_TURNS), key)
                facts, closing = f.result(), c.result()
            spent += facts["cost"] + closing["cost"]
            at += min(max(facts["latency"], closing["latency"]), v2.CLOCK_LATENCY_CAP_S)
            if (facts["parsed"] or {"unsupported": True})["unsupported"]:
                why = "unsupported_fact"
            elif v2.closing_confirmed(closing["parsed"], turns, end, at):
                why = "call_closing"
            elif v2.call_over(at, end[-1]):
                why = "call_over"
            elif v2.after_goodbye(turns, end, at):
                why = "after_goodbye"
            elif card["help"] != "answer" and not rep_could_use_last(at):
                why = "rep_has_last_card"
        if why:
            entry["event"] = f"drop:{why}"
            dropped.append({**card, "why": why})
            continue
        done = finished_by(end, at)
        shown.append({"visible_t": round(at, 1), "after_turn": turns[max(0, done - 1)]["id"], "kind": card["act"], "say": card["say"],
                      "source": card["source"], "source_quote": card["source_quote"], "objective": card["objective"], "born_t": start,
                      "situation": out["situation"], "priority": out["priority"], "checks": out["checks"],
                      "last_move": out["last_move"], "their_answer": out["their_answer"],
                      "playbook_example": v2.playbook_example(sources, card),
                      "reaction_s": round(at - max((end[i] for i, t in enumerate(turns) if t["who"] == "them" and end[i] <= start + 1e-6), default=start), 1)})
        entry["event"] = "shown"
    return {"id": call["id"], "mode": "min", "readings": readings, "shown": shown, "notes": notes, "dropped": dropped,
            "duration": end[-1], "cost": spent}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--only", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    from evals.copilot.run import load_production_provider

    load_production_provider()
    from app.services.copilot.playbook_objections import custom_entries
    from app.services.playbooks.live import live_snapshot
    from evals.copilot.export_calls import supabase

    calls = [json.loads((CALLS / f"{c}.local.json").read_text(encoding="utf-8")) for c in args.only.split(",")]
    contexts = [context_for({**c, "playbook_version_id": None}).replace("GOAL:", "USUAL GOAL FOR THIS TYPE OF CALL (a starting point, not an obligation):", 1)
                for c in calls]
    custom = custom_entries(live_snapshot(supabase(), calls[0]["company_id"], calls[0]["motion"]))
    for c in calls:
        semantic.turn_readings(c, custom)
    played = [play(c, ctx, v2.playbook_intent(ctx), custom) for c, ctx in zip(calls, contexts)]
    Path(args.out).write_text(json.dumps({"mode": "min", "version": "min-3", "model": v2.MODEL, "played": played},
                                         ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    for p in played:
        lat = sorted(r["latency"] for r in p["readings"] if not r["error"])
        print(f"{p['id']}: {len(p['readings'])} readings; shown {len(p['shown'])}; latency p50 {lat[len(lat) // 2]:.1f} s "
              f"p90 {lat[int(len(lat) * 0.9)]:.1f} s; ${p['cost']:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
