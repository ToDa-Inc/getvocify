"""Offline experiment: a contextual "strategic brain" (understand + judge in one reading) behind an intervention gate,
replayed over real calls in simulated time. Nothing here is used by the app; the fast path (points) is unchanged.

    cd backend && PATH=$HOME/.railway/bin:$PATH python -m evals.strategic.run --config B --out b.json
    python -m evals.strategic.run --config C --only 816ba4f7 --out c.json
    python -m evals.strategic.run --paired c.json --out paired.json     # same state, reasoning none vs high

B: reasoning none; C: reasoning high; same model, prompt and gate. Readings are one at a time, latest words win (as the
island's reader): a reading starts when the other side ends a turn (or the rep has said enough), reads the turns finished
by then, and its result becomes visible after the model's real latency. Turns finished meanwhile go through the gate.
Reads the database (company playbook, knowledge, offer); writes nothing. Calls are evals/copilot/calls/*.local.json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
from pathlib import Path

import httpx

CALLS = Path(__file__).resolve().parents[1] / "copilot" / "calls"
MODEL = "deepseek-ai/DeepSeek-V4.1-Flash-1017"
CONFIGS = {"B": "none", "C": "high"}
ANSWER_TOKENS, THINK_TOKENS = 2200, 8000
PROSPECT_WORDS, REP_WORDS, REP_GAP_S = 4, 8, 6.0
MIN_GAP_S, DUPLICATE_WINDOW_S, RECENT_S = 20.0, 90.0, 120.0
SECONDS_PER_WORD = 0.33

SYSTEM = """You are the strategic judgement of a live conversation assistant. A professional ("the rep") is in a live
conversation with "the other side". A separate fast assistant already answers direct questions and objections within a
second; that is not your job. Your job is the direction of the conversation: you read it as it unfolds, keep an accurate
picture of what is going on, and decide whether ONE short intervention right now would clearly improve what the rep does
next. Most of the time it would not. Silence is the default and usually the right answer.

AUTHORITY
- What the conversation shows has authority over how the situation is read, never over the company's mandatory rules
  (claims about the product, prices, policies): you may say nothing about the company that the SOURCES do not say.
- You may reconsider hypotheses, change strategy, skip playbook steps that no longer apply, and recommend letting go of a
  goal that is no longer reasonable in this conversation. You never change company policy and never treat what someone
  said as a confirmed fact. Every deviation from the playbook rests on evidence from this conversation.
- The playbook describes what a good conversation usually looks like; you decide what THIS conversation needs.

STATE (your memory between readings)
- observations: what was said, verbatim, who said it, the turn id. These are the only facts, and a quote only proves
  that someone said it, not that it is true. Mark attribution "doubtful" when the text looks garbled or mistranscribed.
  Hypothetical, ironic or invented examples ("me lo invento", "imagina que…") are observations of a hypothetical.
- interpretations: what you infer, each citing observation ids. Never facts.
- hypotheses: the needs or reasons this conversation could be about. Seed them from the OFFER and PLAYBOOK; one that
  emerges from the call has source "call". Status unknown | supported | contradicted | mixed, with the observation ids
  for and against. New evidence is added, it never erases older evidence.
- dynamics: how the interaction is going (who talks, monologues, interest, time, phase), from the words and from the
  measured DYNAMICS.
- strategy: the goal as it stands now and the direction that makes sense.
PREVIOUS STATE is your own earlier reading. Treat it as conclusions to RE-CHECK against the conversation, not as truth:
keep only what you can still cite, drop or downgrade what the conversation no longer supports. Keep the ids of what you keep.

DIFFERENT DECISIONS NEED DIFFERENT EVIDENCE
- Stop pushing one pain or argument: enough evidence that this line does not fit (once can be enough).
- Disqualify the opportunity as a whole: only when no relevant need remains after a reasonable exploration.
- Reopen a hypothesis: new information justifies it.
- The other side clearly does not want to go on: respect it at once.
- Change direction without arbitrarily changing the goal; drop a strategy without necessarily dropping the opportunity.
  The goal changes only when the conversation's purpose changed, never because a step is still pending.

WHEN TO INTERVENE (all of these)
- Something changed: a fact, a contradiction, a buying signal, a refusal, an opening the rep is missing; OR the dynamics
  call for it (a long rep monologue, interest fading, time running out, a phase that should change).
- The rep is not already doing it, and it was not already shown (SHOWN SO FAR) while still valid.
- It helps now, not later, and it is worth pulling the rep's eyes off the conversation for two seconds.
Never intervene with generic sales advice, to answer a direct question (the fast assistant does that), or to repeat yourself.

OUTPUT: only valid JSON, keys in this order. "action" and "say" in the conversation's language; the rest in English.
{"observations": [{"id": "o1", "turn": turn id, "who": "them"|"you", "quote": verbatim, at most 25 words, "attribution": "clear"|"doubtful"}],
 "interpretations": [{"text": at most 20 words, "from": [observation ids]}],
 "hypotheses": [{"id": "h1", "text": at most 15 words, "source": "company"|"call", "status": "unknown"|"supported"|"contradicted"|"mixed", "for": [ids], "against": [ids]}],
 "dynamics": at most 25 words,
 "strategy": {"goal_now": at most 15 words, "direction": at most 20 words},
 "decision": {"act": "silence"|"intervene", "kind": "reconsider"|"deepen"|"next_step"|"drop_line"|"disqualify"|"respect_exit"|"refocus"|"other"|null,
   "trigger": what changed, at most 12 words, "evidence": [observation ids], "action": what the rep should do, at most 10 words,
   "say": words the rep could say, at most 18 words, or "", "valid_while": at most 12 words, "importance": "high"|"normal"}}
Keep at most 30 observations (the ones that matter). When "act" is "silence", the other decision fields are null or empty."""

REVALIDATE_SYSTEM = """A live assistant prepared ONE intervention for a salesperson, reading the conversation up to a point.
While it was being prepared, the conversation went on. Decide whether to still show it NOW: it must still fit what was
just said, still be useful, and the rep must not already be doing it. When unsure, drop it.
Answer only JSON: {"verdict": "show"|"drop", "why": at most 10 words}"""


# ---------- the call in time ----------


def words(text: str) -> int:
    return len(text.split())


def ends(turns: list[dict]) -> list[float]:
    """When each turn finished: the next turn's start, or its own start plus its words."""
    out = []
    for i, t in enumerate(turns):
        own = t["t"] + max(0.45, words(t["text"]) * SECONDS_PER_WORD)
        out.append(max(own, turns[i + 1]["t"]) if i + 1 < len(turns) else own)
    return out


def triggers(turns: list[dict], end: list[float]) -> list[float]:
    """The moments a reading is asked for: the other side ends a turn, or the rep has said enough since the last one."""
    out, rep_words, last_rep_t = [], 0, -1e9
    for i, t in enumerate(turns):
        final = i + 1 >= len(turns) or turns[i + 1]["who"] != t["who"]
        if t["who"] == "them":
            if final and words(t["text"]) >= PROSPECT_WORDS:
                out.append(end[i])
        else:
            rep_words += words(t["text"])
            if final and rep_words >= REP_WORDS and end[i] - last_rep_t >= REP_GAP_S:
                out.append(end[i])
                rep_words, last_rep_t = 0, end[i]
    return sorted(set(out))


def finished_by(end: list[float], at: float) -> int:
    """How many turns had finished at this time."""
    return sum(1 for e in end if e <= at + 1e-6)


def dynamics(turns: list[dict], upto: int, end: list[float], now: float) -> str:
    seen = turns[:upto]
    if not seen:
        return "(nothing said yet)"
    rep = sum(words(t["text"]) for t in seen if t["who"] == "you")
    them = sum(words(t["text"]) for t in seen if t["who"] == "them")
    recent = [t for i, t in enumerate(seen) if end[i] >= now - RECENT_S]
    rep_r = sum(words(t["text"]) for t in recent if t["who"] == "you")
    them_r = sum(words(t["text"]) for t in recent if t["who"] == "them")
    # The rep's current stretch: their words since the other side last said something substantial.
    stretch, since = 0, None
    for i in range(len(seen) - 1, -1, -1):
        t = seen[i]
        if t["who"] == "them" and words(t["text"]) >= PROSPECT_WORDS:
            break
        if t["who"] == "you":
            stretch += words(t["text"])
            since = t["t"]
    last_them = next((end[i] for i in range(len(seen) - 1, -1, -1) if seen[i]["who"] == "them" and words(seen[i]["text"]) >= PROSPECT_WORDS), None)
    questions = sum(t["text"].count("?") for t in seen if t["who"] == "you")
    them_turns = [words(t["text"]) for t in seen if t["who"] == "them" and words(t["text"]) >= 2]
    first5 = sum(them_turns[:5]) / max(1, len(them_turns[:5]))
    last5 = sum(them_turns[-5:]) / max(1, len(them_turns[-5:]))
    share = lambda a, b: f"{round(100 * a / max(1, a + b))}%"
    return "\n".join([
        f"- Elapsed: {round(now)} s",
        f"- Rep share of words: whole call {share(rep, them)}, last {int(RECENT_S)} s {share(rep_r, them_r)}",
        f"- Rep's current stretch since the other side last spoke at length: {stretch} words"
        + (f" over {round(now - since)} s" if since is not None and stretch else ""),
        f"- Seconds since the other side last said something substantial: {round(now - last_them) if last_them else 'never'}",
        f"- Questions the rep asked so far: {questions}",
        f"- Other side's words per turn: first turns {first5:.0f}, latest turns {last5:.0f}",
    ])


# ---------- one call ----------


def context_for(call: dict) -> str:
    from evals.copilot import live_brain_run as run
    from app.services.copilot import live_brain as brain
    from app.services.copilot.live_models import LiveReading

    from evals.strategic.history import as_of_call, reliable_reads

    reliable_reads()
    client, sb, membership, api = run.client_for(call)
    stub = LiveReading(call_id=call["id"], sales_motion_key=call["motion"], call_mode=call["call_mode"], turns=call["turns"][:1])
    ctx = as_of_call(asyncio.run(api._brain_context(sb, membership, stub)), call, sb, membership.company_id)
    return brain.playbook_header(ctx.snapshot, call["motion"], None) + "\n\n" + run.sources_text(ctx)


def ask_model(system: str, user: str, effort: str, max_tokens: int) -> dict:
    payload = {
        "model": MODEL, "temperature": 0.2, "max_tokens": max_tokens, "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}], "reasoning_effort": effort,
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
            from app.services.llm.shared import extract_json

            content = body["choices"][0]["message"].get("content") or ""
            details = (body.get("usage") or {}).get("completion_tokens_details") or {}
            return {"parsed": extract_json(content) if content.strip() else None, "latency": latency,
                    "reasoning_tokens": details.get("reasoning_tokens") or 0, "error": None if content.strip() else "empty"}
        except Exception as exc:  # retried; a reading that fails is recorded, not hidden
            last = repr(exc)[:200]
            time.sleep(5 * (attempt + 1))
    return {"parsed": None, "latency": 0.0, "reasoning_tokens": 0, "error": last}


def transcript(turns: list[dict]) -> str:
    return "\n".join(f"[{t['id']}] {'Them' if t['who'] == 'them' else 'You'}: {' '.join(t['text'].split())}" for t in turns) or "(empty)"


def reading_input(sources: str, turns: list[dict], upto: int, end: list[float], now: float, previous: dict | None, shown: list[dict]) -> str:
    shown_lines = "\n".join(f"- after {s['after_turn']} ({round(s['visible_t'])} s): [{s['kind']}] {s['action']} — «{s['say']}»" for s in shown) or "(none)"
    prev = json.dumps({k: previous.get(k) for k in ("observations", "interpretations", "hypotheses", "dynamics", "strategy")}, ensure_ascii=False) if previous else "(first reading)"
    return (f"{sources}\n\nCONVERSATION SO FAR (\"You\" is the rep):\n{transcript(turns[:upto])}\n\n"
            f"DYNAMICS (measured):\n{dynamics(turns, upto, end, now)}\n\nSHOWN SO FAR (interventions the rep already saw):\n{shown_lines}\n\n"
            f"PREVIOUS STATE (re-check it):\n{prev}")


def gate(decision: dict, state: dict, turns: list[dict], upto: int, ready_at: float, end: list[float], shown: list[dict]) -> tuple[bool, str, dict | None]:
    from app.services.copilot.live_brain import quote_in

    by_id = {o.get("id"): o for o in state.get("observations") or [] if isinstance(o, dict)}
    cited = [by_id[e] for e in decision.get("evidence") or [] if e in by_id]
    seen = {t["id"]: t["text"] for t in turns[:upto]}
    if not cited or not all(o.get("turn") in seen and quote_in(o.get("quote"), seen[o["turn"]]) for o in cited):
        return False, "evidence_unverified", None
    text = f"{decision.get('action') or ''} {decision.get('say') or ''}"
    for s in shown:
        if ready_at - s["visible_t"] <= DUPLICATE_WINDOW_S and SequenceMatcher(None, text.lower(), f"{s['action']} {s['say']}".lower()).ratio() > 0.6:
            return False, "duplicate", None
    if shown and ready_at - shown[-1]["visible_t"] < MIN_GAP_S and decision.get("importance") != "high":
        return False, "too_soon", None
    new = [t for i, t in enumerate(turns) if i >= upto and end[i] <= ready_at and words(t["text"]) >= 3]
    if not new:
        return True, "fresh", None
    user = (f"CONVERSATION UP TO WHERE IT WAS PREPARED:\n{transcript(turns[max(0, upto - 12):upto])}\n\n"
            f"THE INTERVENTION: action «{decision.get('action')}»; say «{decision.get('say')}»; because «{decision.get('trigger')}»\n\n"
            f"SAID SINCE (while it was prepared):\n{transcript(new)}")
    check = ask_model(REVALIDATE_SYSTEM, user, "none", 120)
    verdict = (check["parsed"] or {}).get("verdict")
    return verdict == "show", f"revalidated_{verdict or 'unsure'}", {"latency": check["latency"], "why": (check["parsed"] or {}).get("why")}


def play(call: dict, effort: str, sources: str) -> dict:
    turns = call["turns"]
    end = ends(turns)
    asks = triggers(turns, end)
    readings, shown = [], []
    previous, clock, pending = None, 0.0, list(asks)
    while pending:
        start = max(clock, pending[0])
        pending = [p for p in pending if p > start]  # every trigger up to now is served by this reading (latest words win)
        upto = finished_by(end, start)
        result = ask_model(SYSTEM, reading_input(sources, turns, upto, end, start, previous, shown), effort,
                           ANSWER_TOKENS + (THINK_TOKENS if effort != "none" else 0))
        ready_at = start + result["latency"]
        state = result["parsed"] if isinstance(result["parsed"], dict) else None
        entry = {"start_t": start, "upto": upto, "after_turn": turns[upto - 1]["id"] if upto else None, "latency": result["latency"],
                 "reasoning_tokens": result["reasoning_tokens"], "error": result["error"], "state": state, "gate": None}
        if state:
            previous = state
            decision = state.get("decision") or {}
            if decision.get("act") == "intervene":
                ok, why, extra = gate(decision, state, turns, upto, ready_at, end, shown)
                entry["gate"] = {"shown": ok, "why": why, **({"revalidation": extra} if extra else {})}
                if ok:
                    visible = ready_at + (extra["latency"] if extra else 0.0)
                    by_id = {o.get("id"): o for o in state.get("observations") or [] if isinstance(o, dict)}
                    shown.append({"visible_t": visible, "after_turn": turns[finished_by(end, visible) - 1]["id"], "read_upto": entry["after_turn"],
                                  "kind": decision.get("kind"), "action": decision.get("action") or "", "say": decision.get("say") or "",
                                  "trigger": decision.get("trigger"), "importance": decision.get("importance"),
                                  "evidence": [by_id[e].get("quote") for e in decision.get("evidence") or [] if e in by_id]})
        readings.append(entry)
        clock = ready_at
    return {"id": call["id"], "effort": effort, "readings": readings, "shown": shown, "duration": end[-1]}


def paired(source: dict, per_call: int) -> list[dict]:
    """Same state, same moment: reasoning none vs high, at readings spread over each call (states taken from `source`)."""
    rows = []
    random.seed(7)
    for played in source["played"]:
        call = json.loads((CALLS / f"{played['id']}.local.json").read_text(encoding="utf-8"))
        sources, turns = context_for(call), call["turns"]
        end = ends(turns)
        readings = [r for r in played["readings"] if r["state"]]
        picks = sorted(set(int(i * (len(readings) - 1) / max(1, per_call - 1)) for i in range(per_call))) if readings else []
        for k in picks:
            r = readings[k]
            previous = readings[k - 1]["state"] if k else None
            shown = [s for s in played["shown"] if s["visible_t"] <= r["start_t"]]
            user = reading_input(sources, turns, r["upto"], end, r["start_t"], previous, shown)
            for effort in ("none", "high"):
                out = ask_model(SYSTEM, user, effort, ANSWER_TOKENS + (THINK_TOKENS if effort != "none" else 0))
                rows.append({"call": played["id"], "upto": r["upto"], "after_turn": r["after_turn"], "effort": effort,
                             "latency": out["latency"], "decision": (out["parsed"] or {}).get("decision"), "error": out["error"]})
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--config", choices=sorted(CONFIGS))
    parser.add_argument("--only", default="816ba4f7,5c013cf3,proto,0a187842,281116db")
    parser.add_argument("--paired", help="a --config run's JSON whose states the paired test reuses")
    parser.add_argument("--per-call", type=int, default=8)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from evals.copilot.run import load_production_provider

    load_production_provider()  # COPILOT_DIRECT_* before the app reads its settings
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    if args.paired:
        rows = paired(json.loads(Path(args.paired).read_text(encoding="utf-8")), args.per_call)
        Path(args.out).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        print(len(rows), "paired readings,", sum(1 for r in rows if r["error"]), "errors")
        return 0
    effort = CONFIGS[args.config]
    calls = [json.loads((CALLS / f"{c}.local.json").read_text(encoding="utf-8")) for c in args.only.split(",")]
    # One at a time: the database client is shared, and a failed read would leave a call without its playbook.
    contexts = [context_for(c) for c in calls]
    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        played = list(pool.map(lambda pair: play(pair[0], effort, pair[1]), zip(calls, contexts)))
    Path(args.out).write_text(json.dumps({"config": args.config, "model": MODEL, "effort": effort, "played": played}, ensure_ascii=False, indent=1), encoding="utf-8")
    for p in played:
        lat = sorted(r["latency"] for r in p["readings"] if not r["error"])
        print(f"{p['id']}: {len(p['readings'])} readings ({sum(1 for r in p['readings'] if r['error'])} errors), "
              f"{sum(1 for r in p['readings'] if (r['state'] or {}).get('decision', {}).get('act') == 'intervene')} wanted to intervene, "
              f"{len(p['shown'])} shown, latency p50 {lat[len(lat)//2] if lat else 0:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
