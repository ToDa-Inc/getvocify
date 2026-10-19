"""Play real calls through the live call assistant's producers and check the spec's gates.

    cd backend && PATH=$HOME/.railway/bin:$PATH python -m evals.copilot.live_brain_run --production-provider
    python -m evals.copilot.live_brain_run --production-provider --only proto,9f125ca1 --no-judge

Real: the /copilot/live/points, /live/progress and /live/recap endpoints (router, prompts, checks, model) asked in the order the
renderer will ask them, as the call's own rep, with the rep's published playbook, knowledge and offer read from the database;
the state is carried through the call by the same code the dashboard uses (shared/live-call/state.js, run with node). Calls
come from `calls/*.local.json` (see export_calls.py: customer speech, gitignored). Nothing is written to the database.
Always pass --production-provider: the brain's model path is direct Together with reasoning off, OpenRouter only as its backup.

Gates (docs/superpowers/specs/2026-10-16-live-call-assistant-design.md, "Order of work" 1):
  invented facts 0         every line the brain wrote (points, Ahora, recap) is checked against what it was given: numbers
                           in code, claims by a judge model (Sonnet via OpenRouter; this is the only OpenRouter use)
  duplicate points 0       no two points in a call for the same thing said
  decisions vs labels      `labels.json`: the moments with the decision a person says is right (Dani confirms; until a label
                           is `confirmed` the agreement is reported as provisional)
  latency                  points: p90 of the model time at most 1.1 s (today's card); progress: p90 at most 3 s

The "Qué decir" view (build contract 2026-10-20 §2; on by default, --no-say-view for the tabs view's readings):
  go deeper                fires per call, each with the turn it came from (the details report), and a judge's verdict on each
                           trigger: ordinary sentence / a figure already given / the rep already following up / worth going deeper
  rewrite                  for the first points of each call, the same point from another angle (version 2, and 3 for two of them):
                           latency, how many had no honest other angle, inventions (the same checks as every line)
  ask_step                 two pending items at half way and at the end of each call: latency (bar p90 1.1 s), questions, inventions
  next                     Responder readings with nothing to answer (the labelled taps, and one a quarter, half and three
                           quarters into each call): the next best question
  parts                    steps whose criterion lists parts: the parts the aids found and those heard with evidence
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import statistics
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).parent
CALLS = HERE / "calls"
LABELS = HERE / "labels.json"
STATE_CLI = Path(__file__).resolve().parents[3] / "shared/live-call/cli.mjs"
WINDOW_HEAD_CHARS, WINDOW_TAIL_CHARS = 3000, 12000
RESPOND_WINDOW_S = 60.0
POINTS_P90_MS, PROGRESS_P90_MS = 1100, 3000
REWRITES_PER_CALL, SECOND_REWRITES_PER_CALL, STEP_ITEMS_PER_MOMENT = 4, 2, 2
MIN_PROSPECT_WORDS, MIN_REP_WORDS = 4, 12
JUDGE_MODEL = "anthropic/claude-sonnet-5.5"


def js(op: str, state=None, result=None, **args):
    """One of shared/live-call/state.js's operations, run with node."""
    out = subprocess.run(
        ["node", str(STATE_CLI)], input=json.dumps({"op": op, "state": state, "result": result, "args": args}),
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


def sse_frames(text: str) -> list[dict]:
    return [json.loads(block[6:]) for block in text.split("\n\n") if block.startswith("data: ")]


def window_of(turns: list[dict]) -> list[dict]:
    """Head and tail of a long call as the client keeps it (src/lib/live-assist.ts windowOf: 3000 + 12000 characters, whole lines)."""
    size = [len(t["text"]) + 12 for t in turns]
    if sum(size) <= WINDOW_HEAD_CHARS + WINDOW_TAIL_CHARS:
        return turns
    head, used = 0, 0
    while head < len(turns) and used + size[head] <= WINDOW_HEAD_CHARS:
        used += size[head]
        head += 1
    tail, used = len(turns), 0
    while tail > head and used + size[tail - 1] <= WINDOW_TAIL_CHARS:
        tail -= 1
        used += size[tail]
    return turns[:head] + turns[tail:]


def words(text: str) -> int:
    return len(text.split())


def pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))]


# ---------- setup ----------


def load_production_provider() -> None:
    from evals.copilot.run import load_production_provider as load

    load()


def client_for(call: dict):
    sys.path.insert(0, str(HERE.parents[1]))
    from dotenv import load_dotenv

    load_dotenv(HERE.parents[1] / ".env")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from supabase import create_client

    from app.api import copilot as copilot_api
    from app.deps import get_membership, get_supabase, get_user_id
    from app.services.company import CompanyService

    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    membership = CompanyService(sb).require_membership(call["user_id"])
    app = FastAPI()
    app.include_router(copilot_api.router)
    app.dependency_overrides[get_user_id] = lambda: call["user_id"]
    app.dependency_overrides[get_membership] = lambda: membership
    app.dependency_overrides[get_supabase] = lambda: sb
    # Nothing of this run is logged: the database this reads may be production's.
    from app.config import settings

    settings.COPILOT_LOG_EVENTS = False
    # The flag is the company's in production; here it is on for the rep being played.
    copilot_api.is_enabled = lambda *_a, **_k: True
    return TestClient(app), sb, membership, copilot_api


def sources_text(ctx) -> str:
    """Everything the producers were allowed to claim from: the same blocks the prompts carry."""
    from app.services.copilot import live_brain as brain

    return "\n\n".join([
        brain.context_blocks(product_context=ctx.product_context, knowledge=ctx.knowledge, history=ctx.history, call_text=""),
        brain.entries_block(ctx.snapshot) if ctx.snapshot else "",
        brain.steps_block(ctx.snapshot) if ctx.snapshot else "",
        brain.qualification_block(ctx.snapshot) if ctx.snapshot else "",
        ctx.today,
    ])


# ---------- one call ----------


def point_in(point: dict, versions: list[str]) -> dict:
    """A point as a rewrite reads it: the shared state's pointsIn plus its source and every version the rep has seen."""
    return {"id": point["id"], "kind": point["kind"], "tag_key": point["tag_key"], "title": point["title"], "turn_ids": point["turn_ids"],
            "outcome": "open", "say": versions[0], "source_id": (point.get("source") or {}).get("id"), "versions": versions}


def play(call: dict, only_asks: list[dict], say_view: bool = True) -> dict:
    client, sb, membership, api = client_for(call)
    from app.services.copilot.live_models import LiveReading

    turns = call["turns"]
    stub = LiveReading(call_id=call["id"], sales_motion_key=call["motion"], call_mode=call["call_mode"], turns=turns[:1])
    ctx = asyncio.run(api._brain_context(sb, membership, stub))
    base = {"call_id": call["id"], "sales_motion_key": call["motion"], "call_mode": call["call_mode"], "language": "es", "say_view": say_view}
    heard: dict[str, list[str]] = {}  # the parts of steps heard in this call (step id -> part ids), for the report
    asked: dict[str, list[dict]] = {"rewrite": [], "ask_step": []}

    state = js("empty", call_id=call["id"])
    readings: list[dict] = []
    covered = -1  # the last turn index a points reading has already covered
    asks = {anchor(call, a) for a in only_asks if a.get("ask") == "responder"}

    def post(path: str, body: dict):
        t0 = time.perf_counter()
        response = client.post(f"/api/v1/copilot/live/{path}", json=body)
        wall = int((time.perf_counter() - t0) * 1000)
        if response.status_code != 200:
            return None, wall, f"HTTP {response.status_code}: {response.text[:160]}"
        if path == "points":
            frames = sse_frames(response.text)
            result = next((f for f in reversed(frames) if f["type"] == "result"), None)
            error = next((f["message"] for f in frames if f["type"] == "error"), None)
            return result, wall, error
        return response.json(), wall, None

    def reading(idx: int, producer: str, reason: str, focus: int | None = None, asked: bool = False):
        nonlocal state, covered
        upto = turns[: idx + 1]
        body = {
            **base, "reason": reason, "turns": window_of(upto), "state_version": state["version"], "type_changed": False,
            "cursor": state["cursors"]["points" if producer == "points" else "progress"],
            "points": js("pointsIn", state), "progress": js("progressIn", state),
            **({"focus_from": upto[focus]["id"]} if focus is not None else {}),
        }
        result, wall, error = post(producer, body)
        entry = {"turn": upto[-1]["id"], "idx": idx, "producer": producer, "reason": reason, "wall_ms": wall, "error": error}
        if result:
            entry.update(model_ms=result.get("latency_ms"), model=result.get("model"), skipped=result.get("skipped"), guards=result.get("guards") or {})
            if producer == "points":
                entry.update(new=[p for p in result["points"] if not p.get("is_update")], updates=[p for p in result["points"] if p.get("is_update")],
                             closed=result["closed"], nothing=result.get("nothing"), next=result.get("next"))
                state = js("applyPoints", state, result, asked=asked)
            else:
                entry.update(steps=result.get("steps"), data=result.get("data"), goal=result.get("goal"), now=result.get("now"), missing=result.get("missing"),
                             aids=bool(result.get("aids")), aids_parts={k: v for k, v in ((result.get("aids") or {}).get("steps") or {}).items() if v.get("parts")})
                for step in result.get("steps") or []:
                    for part in step.get("parts") or []:
                        if part["done"] and part["id"] not in heard.setdefault(step["id"], []):
                            heard[step["id"]].append(part["id"])
                state = js("applyProgress", state, result)
                entry["now_kept"] = (result.get("guards") or {}).get("now_kept", 0)
        readings.append(entry)
        return entry

    # Responder taps besides the labelled ones: at the end of a prospect turn a quarter, half and three quarters into the call.
    ends = [i for i, t in enumerate(turns) if t["who"] == "them" and words(t["text"]) >= MIN_PROSPECT_WORDS
            and (i + 1 >= len(turns) or turns[i + 1]["who"] != "them")]
    taps = {ends[int(len(ends) * q)]: True for q in (0.25, 0.5, 0.75)} if ends else {}
    for i, turn in enumerate(turns):
        ended = i + 1 >= len(turns) or turns[i + 1]["who"] != turn["who"]
        if not ended:
            continue
        if turn["who"] == "them" and words(turn["text"]) >= MIN_PROSPECT_WORDS:
            first_unread = max(0, covered)
            reading(i, "points", "turn_end", focus=first_unread)
            covered = i
            reading(i, "progress", "turn_end")
        elif turn["who"] == "you" and words(turn["text"]) >= MIN_REP_WORDS:
            if any(p["outcome"] in ("open", "unanswered") for p in state["points"]):
                reading(i, "points", "rep_turn", focus=max(0, covered))
            reading(i, "progress", "rep_turn")
        if (turn["id"] in asks or i in taps) and turn["who"] == "them":
            start = next((j for j, t in enumerate(turns) if t["t"] >= turn["t"] - RESPOND_WINDOW_S), 0)
            reading(i, "points", "responder", focus=start, asked=True)
    def asked_reading(kind: str, idx: int, extra: dict) -> dict:
        upto = turns[: idx + 1]
        body = {**base, "reason": kind, "turns": window_of(upto), "state_version": state["version"], "progress": js("progressIn", state), **extra}
        result, wall, error = post("points", body)
        got = (result or {}).get("rewrite" if kind == "rewrite" else "step_question")
        entry = {"turn": upto[-1]["id"], "idx": idx, "wall_ms": wall, "error": error, "model_ms": (result or {}).get("latency_ms"),
                 "model": (result or {}).get("model"), "guards": (result or {}).get("guards") or {}, "got": got, **extra}
        asked[kind].append(entry)
        return entry

    # Rewrite: Responder pressed on a card already shown, a few seconds after it appeared (the turns up to the next one).
    index = {t["id"]: n for n, t in enumerate(turns)}
    shown = [p for p in state["points"] if p.get("answer") or p.get("fallback")]
    for n, point in enumerate(shown[:REWRITES_PER_CALL]):
        idx = min(len(turns) - 1, max(index[t] for t in point["turn_ids"]) + 1)
        versions = [point.get("answer") or point.get("fallback")]
        first = asked_reading("rewrite", idx, {"points": [point_in(point, versions)], "target": {"point_id": point["id"], "version": 1}})
        if first["got"] and n < SECOND_REWRITES_PER_CALL:
            versions = versions + [first["got"]["answer"]]
            asked_reading("rewrite", idx, {"points": [point_in(point, versions)], "target": {"point_id": point["id"], "version": 2}})
    # Pasos: a question for pending items, half way and at the end.
    snapshot = ctx.snapshot or {}
    # Only the steps the island lists live (a step about delivery stays for coaching).
    coaching = {i for i, a in ((state["progress"].get("aids") or {}).get("steps") or {}).items() if a.get("live") is False}
    for idx in sorted({len(turns) // 2, len(turns) - 1}):
        done = set(state["progress"]["steps"]) | set(state["progress"]["data"]) | coaching
        pending = [("step", s["step_id"]) for s in snapshot.get("steps") or [] if s.get("step_id") not in done]
        pending_data = [("data", q["criterion_id"]) for q in snapshot.get("qualification") or [] if q.get("criterion_id") not in done]
        for kind, ident in (pending[:1] + pending_data[:1] + pending[1:])[:STEP_ITEMS_PER_MOMENT]:
            asked_reading("ask_step", idx, {"target": {"kind": kind, "id": ident}})

    # Resumen at the end and half way through: the recap on request.
    recaps = []
    for idx in sorted({len(turns) // 2, len(turns) - 1}):
        upto = turns[: idx + 1]
        result, wall, error = post("recap", {**base, "reason": "resumen", "turns": window_of(upto), "progress": js("progressIn", state), "up_to": upto[-1]["id"]})
        recaps.append({"turn": upto[-1]["id"], "result": result, "wall_ms": wall, "error": error})
    return {"call": call, "state": state, "readings": readings, "recaps": recaps, "asked": asked, "heard": heard, "ctx": {"sources": sources_text(ctx), "has_playbook": bool(ctx.snapshot),
            "version": ctx.playbook_version_id, "steps": len((ctx.snapshot or {}).get("steps") or []), "steps_list": (ctx.snapshot or {}).get("steps") or [],
            "data": len((ctx.snapshot or {}).get("qualification") or [])}}


# ---------- checks ----------

NUMBER = re.compile(r"\d+")


def norm(text: str) -> str:
    import unicodedata

    plain = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", plain.lower()).split())


def lines_of(played: dict) -> list[dict]:
    """Every line the brain wrote for the rep, with the part of the call that existed when it was written."""
    turns = played["call"]["turns"]
    index = {t["id"]: n for n, t in enumerate(turns)}
    out = []
    for point in played["state"]["points"]:
        text = point.get("answer") or point.get("fallback")
        if text:
            out.append({"kind": "point", "id": point["id"], "text": text, "grounded": bool(point.get("answer")), "upto": max(index[t] for t in point["turn_ids"])})
    for r in played["readings"]:
        if r["producer"] == "progress" and r.get("now") and r["now"].get("say"):
            out.append({"kind": "ahora", "id": r["now"]["id"], "text": r["now"]["say"], "grounded": True, "upto": r["idx"]})
    for rc in played["recaps"]:
        for line in (rc["result"] or {}).get("lines") or []:
            out.append({"kind": "recap", "id": rc["turn"], "text": line, "grounded": True, "upto": index[rc["turn"]]})
    for r in played["readings"]:
        if r["producer"] == "points" and r.get("next") and r["next"].get("question"):
            out.append({"kind": "next", "id": r["next"]["id"], "text": r["next"]["question"], "grounded": True, "upto": r["idx"]})
    for kind, field in (("rewrite", "answer"), ("ask_step", "question")):
        for a in played["asked"][kind]:
            if a["got"] and a["got"].get(field):
                out.append({"kind": kind, "id": a["got"].get("point_id") or a["got"].get("id"), "text": a["got"][field], "grounded": True, "upto": a["idx"]})
    from app.services.copilot.live_points import similar

    examples = [s["example"] for s in played["ctx"].get("steps_list") or [] if s.get("example")]
    for line in out:
        # Ahora's line is the playbook step's own sentence (the spec shows the example as the line to say): it is sourced from the
        # playbook, not claimed by the model. Reported on its own, because an example can presume what this call has not shown.
        line["from_example"] = line["kind"] == "ahora" and any(similar(line["text"], e, 0.6) for e in examples)
    seen, unique = set(), []
    for line in out:
        key = (line["kind"], line["id"], norm(line["text"]))
        if key not in seen:
            seen.add(key)
            unique.append(line)
    return unique


def numbers_invented(line: dict, played: dict) -> list[str]:
    """Numbers in a line that are in neither the sources nor the call so far (spelled-out numbers count as said)."""
    from app.services.copilot import live_brain as brain

    allowed = brain.numbers_in(played["ctx"]["sources"] + " " + " ".join(t["text"] for t in played["call"]["turns"][: line["upto"] + 1]))
    return brain.invented_numbers(line["text"], allowed)


JUDGE_SYSTEM = """You check ONE line that a live sales assistant suggested to a salesperson, against what the assistant was allowed to use.
SOURCES are the only things it may state about the company, its product, prices, customers, integrations, dates or promises.
CALL is what had been said so far: facts about the prospect or what was agreed come from it.
A line INVENTS when it states or implies a fact about the company or product (a feature, an integration, a number, a customer, a
date, a guarantee, a yes/no capability) that is in neither SOURCES nor CALL; or claims the prospect said something they did not.
Questions to the prospect, acknowledgements, honest offers to confirm something later, and rewording of what a source says are NOT inventions.
Answer only JSON: {"invented": [short description of each invented claim], "reason": "one short sentence"}"""


def judge(line: dict, played: dict) -> list[str]:
    import httpx

    transcript = "\n".join(f"{'Them' if t['who'] == 'them' else 'You'}: {t['text']}" for t in played["call"]["turns"][: line["upto"] + 1])
    user = f"SOURCES:\n{played['ctx']['sources']}\n\nCALL:\n{transcript[-9000:]}\n\nLINE ({line['kind']}):\n{line['text']}"
    for attempt in range(3):
        try:
            response = httpx.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"}, timeout=90,
                json={"model": JUDGE_MODEL, "temperature": 0, "response_format": {"type": "json_object"},
                      "messages": [{"role": "system", "content": JUDGE_SYSTEM}, {"role": "user", "content": user}]},
            )
            content = response.json()["choices"][0]["message"]["content"]
            from app.services.llm.shared import extract_json

            return [str(x) for x in (extract_json(content).get("invented") or [])]
        except Exception as exc:  # a judge that fails is reported, not counted as a pass
            if attempt == 2:
                return [f"JUDGE FAILED: {exc}"]
            time.sleep(2)
    return []


DEEPEN_JUDGE_SYSTEM = """A live sales assistant showed the salesperson ONE question to go deeper on something the prospect just said.
Judge the prospect's statement that triggered it, given the call so far and the company's playbook steps. One verdict:
- "ordinary": agreement, small talk, their role or company, an answer that already has the detail, or nothing the steps care about.
- "figure_given": they already gave the cause, case or figure the question asks for.
- "rep_following": the rep was already digging into this exact thing (the question repeats what the rep just asked).
- "worth_it": an important statement (a pain, how they work today) said vaguely: going one step deeper helps the call.
Answer only JSON: {"verdict": "ordinary"|"figure_given"|"rep_following"|"worth_it", "reason": "one short sentence"}"""


def deepen_rows(played: dict) -> list[dict]:
    turns = played["call"]["turns"]
    index = {t["id"]: n for n, t in enumerate(turns)}
    rows = []
    for point in played["state"]["points"]:
        if point["kind"] != "deepen":
            continue
        last = max(index[t] for t in point["turn_ids"])
        rows.append({"call": played["call"]["id"], "turn": point["turn_ids"][-1], "said": turns[last]["text"], "title": point["title"],
                     "question": point.get("answer") or point.get("fallback") or "", "step": (point.get("source") or {}).get("id"),
                     "outcome": point["outcome"], "upto": last})
    return rows


def judge_deepen(row: dict, played: dict) -> dict:
    import httpx

    from app.services.llm.shared import extract_json

    transcript = "\n".join(f"{'Them' if t['who'] == 'them' else 'You'}: {t['text']}" for t in played["call"]["turns"][max(0, row["upto"] - 12): row["upto"] + 1])
    steps = "\n".join(f"- {s.get('label')}: {s.get('criterion')}" for s in played["ctx"].get("steps_list") or [])
    user = f"PLAYBOOK STEPS:\n{steps}\n\nCALL (the end is the statement):\n{transcript}\n\nSTATEMENT: {row['said']}\nQUESTION SHOWN: {row['question']}"
    for attempt in range(3):
        try:
            response = httpx.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"}, timeout=90,
                json={"model": JUDGE_MODEL, "temperature": 0, "response_format": {"type": "json_object"},
                      "messages": [{"role": "system", "content": DEEPEN_JUDGE_SYSTEM}, {"role": "user", "content": user}]},
            )
            got = extract_json(response.json()["choices"][0]["message"]["content"])
            return {"verdict": str(got.get("verdict")), "reason": str(got.get("reason") or "")}
        except Exception as exc:
            if attempt == 2:
                return {"verdict": "judge_failed", "reason": str(exc)}
            time.sleep(2)
    return {"verdict": "judge_failed", "reason": ""}


def say_view_summary(played_calls: list[dict], deepen_verdicts: list[dict]) -> dict:
    """The "Qué decir" view's outputs: go deeper, next, rewrite, ask_step and parts."""
    def lat(values: list) -> dict:
        values = [v for v in values if v]
        return {"n": len(values), "p50": pct(values, .5), "p90": pct(values, .9), "max": max(values, default=None)}

    per_call = {p["call"]["id"]: sum(1 for x in p["state"]["points"] if x["kind"] == "deepen") for p in played_calls}
    turn_end = sum(1 for p in played_calls for r in p["readings"] if r["producer"] == "points" and r["reason"] == "turn_end" and not r.get("error"))
    deepen_guards: dict[str, int] = {}
    for p in played_calls:
        for r in p["readings"]:
            for k, v in (r.get("guards") or {}).items():
                if k.startswith("deepen"):
                    deepen_guards[k] = deepen_guards.get(k, 0) + v
    verdicts: dict[str, int] = {}
    for v in deepen_verdicts:
        verdicts[v["verdict"]] = verdicts.get(v["verdict"], 0) + 1
    responder = [r for p in played_calls for r in p["readings"] if r["producer"] == "points" and r["reason"] == "responder" and not r.get("error")]
    nothing = [r for r in responder if not r.get("new") and not r.get("updates")]
    rewrites = [a for p in played_calls for a in p["asked"]["rewrite"]]
    steps = [a for p in played_calls for a in p["asked"]["ask_step"]]
    parts = {p["call"]["id"]: {"steps_with_parts": sorted({k for r in p["readings"] for k in (r.get("aids_parts") or {})}),
                               "parts_heard": sum(len(v) for v in p["heard"].values()),
                               "steps_done_by_parts": sorted(s for s, v in p["state"]["progress"]["steps"].items() if v.get("parts"))}
             for p in played_calls}
    return {
        "deepen": {"total": sum(per_call.values()), "per_call": per_call, "turn_end_readings": turn_end, "guards": deepen_guards, "verdicts": verdicts},
        "next": {"responder_readings": len(responder), "with_nothing_to_answer": len(nothing), "with_next": sum(1 for r in nothing if r.get("next")),
                 "latency": lat([r.get("model_ms") for r in nothing])},
        "rewrite": {"n": len(rewrites), "written": sum(1 for a in rewrites if a["got"]), "none": sum(1 for a in rewrites if not a["got"] and not a["error"]),
                    "errors": sum(1 for a in rewrites if a["error"]), "second": sum(1 for a in rewrites if a["target"]["version"] == 2),
                    "second_written": sum(1 for a in rewrites if a["target"]["version"] == 2 and a["got"]), "latency": lat([a["model_ms"] for a in rewrites]),
                    "guards": {k: sum(a["guards"].get(k, 0) for a in rewrites) for k in {g for a in rewrites for g in a["guards"]}}},
        "ask_step": {"n": len(steps), "written": sum(1 for a in steps if a["got"]), "errors": sum(1 for a in steps if a["error"]),
                     "latency": lat([a["model_ms"] for a in steps]), "wall": lat([a["wall_ms"] for a in steps]),
                     "guards": {k: sum(a["guards"].get(k, 0) for a in steps) for k in {g for a in steps for g in a["guards"]}}},
        "parts": parts,
    }


def duplicates(points: list[dict]) -> list[tuple[str, str]]:
    """Pairs of points that are the same thing said: same kind and type with turns in common, or near-identical words."""
    from app.services.copilot.live_points import similar

    found = []
    for a in range(len(points)):
        for b in range(a + 1, len(points)):
            p, q = points[a], points[b]
            if p["kind"] != q["kind"] or p["tag_key"] != q["tag_key"]:
                continue
            shared = set(p["turn_ids"]) & set(q["turn_ids"])
            if (shared and (p["tag_key"] != "question" or similar(p["title"], q["title"]))) or similar(p["title"], q["title"], 0.8):
                found.append((p["id"], q["id"]))
    return found


def anchor(call: dict, label: dict) -> str | None:
    """The first turn of the other side that contains the label's words."""
    wanted = norm(label["said"])
    return next((t["id"] for t in call["turns"] if t["who"] == "them" and wanted in norm(t["text"])), None)


def agreement(played: dict, labels: list[dict]) -> list[dict]:
    """Each label of this call against what the brain did at that moment."""
    rows = []
    for label in [l for l in labels if l["call"] == played["call"]["id"]]:
        turn_id = anchor(played["call"], label)
        # The point that starts at this turn; failing that, one that merely includes it (a question split by the rep's "ya").
        own = [p for p in played["state"]["points"] if p["turn_ids"][0] == turn_id] if turn_id else []
        within = [p for p in played["state"]["points"] if turn_id in p["turn_ids"]] if turn_id else []
        points = own or ([] if label["expect"]["decision"] == "none" else within)
        got = (points[0]["decision"] or "null") if points else "none"
        want = "null" if label["expect"]["decision"] is None else label["expect"]["decision"]
        rows.append({"label": label, "turn": turn_id, "got": got, "kind": points[0]["kind"] if points else None, "ok": got == want,
                     "title": points[0]["title"] if points else None, "say": (points[0].get("answer") or points[0].get("fallback")) if points else None})
    return rows


def said_order(point: dict, turns_by_id: dict) -> tuple[int, int]:
    """Where a point was said: its first turn, then where its words start inside that turn (as the points producer orders them)."""
    from app.services.copilot.live_points import offset_in

    first = point["turn_ids"][0]
    return turns_by_id[first][0], offset_in(point.get("title") or "", turns_by_id[first][1])


def per_turn(played_calls: list[dict], labels: list[dict]) -> dict:
    """Step 1 of the 2026-10-19 order of work: points per turn that has something, nothing on turns that have nothing,
    short answers, order kept. "Has something" is the brain's own decision (a point was written for that turn); the labels
    add the moments a person marked (unconfirmed until Dani confirms them)."""
    per_turn_counts, lengths, sentences = [], [], []
    readings = fired = out_of_order = 0
    for p in played_calls:
        by_turn: dict[str, int] = {}
        for point in p["state"]["points"]:
            by_turn[point["turn_ids"][0]] = by_turn.get(point["turn_ids"][0], 0) + 1
            text = point.get("answer") or point.get("fallback") or ""
            if text:
                lengths.append(words(text))
                sentences.append(len([s for s in re.split(r"(?<=[.?!])\s+", text.strip()) if s]))
        per_turn_counts += list(by_turn.values())
        index = {t["id"]: (n, t["text"]) for n, t in enumerate(p["call"]["turns"])}
        for r in p["readings"]:
            if r["producer"] != "points" or r["reason"] != "turn_end" or r.get("error"):
                continue
            readings += 1
            fired += bool(r.get("new"))
            order = [said_order(x, index) for x in r.get("new") or []]
            out_of_order += order != sorted(order)
    rows = [row for p in played_calls for row in agreement(p, labels)]
    need = [r for r in rows if r["label"]["expect"]["decision"] != "none"]
    none = [r for r in rows if r["label"]["expect"]["decision"] == "none"]
    dist = {"1": sum(1 for c in per_turn_counts if c == 1), "2": sum(1 for c in per_turn_counts if c == 2), "3+": sum(1 for c in per_turn_counts if c >= 3)}
    return {
        "turns_with_points": len(per_turn_counts), "points_per_turn_with_points": round(sum(per_turn_counts) / len(per_turn_counts), 2) if per_turn_counts else None,
        "per_turn_distribution": dist,
        "turn_end_readings": readings, "turn_end_readings_that_wrote": fired, "results_out_of_order": out_of_order,
        "answer_words": {"n": len(lengths), "p50": pct(lengths, .5), "p90": pct(lengths, .9), "max": max(lengths, default=None),
                         "over_20": sum(1 for n in lengths if n > 20), "over_2_sentences": sum(1 for n in sentences if n > 2)},
        "labels_need_with_point": f"{sum(1 for r in need if r['got'] != 'none')}/{len(need)}",
        "labels_nothing_with_point": f"{sum(1 for r in none if r['got'] != 'none')}/{len(none)}",
    }


# ---------- report ----------


def summarise(played_calls: list[dict], labels: list[dict], judged: dict, deepen_verdicts: list[dict] | None = None) -> dict:
    points_ms = [r["model_ms"] for p in played_calls for r in p["readings"] if r["producer"] == "points" and r["reason"] in ("turn_end", "responder") and r.get("model_ms") and r.get("new")]
    all_points_ms = [r["model_ms"] for p in played_calls for r in p["readings"] if r["producer"] == "points" and r.get("model_ms")]
    progress_ms = [r["model_ms"] for p in played_calls for r in p["readings"] if r["producer"] == "progress" and r.get("model_ms")]
    errors = [(p["call"]["id"], r["turn"], r["producer"], r["error"]) for p in played_calls for r in p["readings"] if r["error"]]
    errors += [(p["call"]["id"], a["turn"], kind, a["error"]) for p in played_calls for kind in ("rewrite", "ask_step") for a in p["asked"][kind] if a["error"]]
    dup = {p["call"]["id"]: duplicates(p["state"]["points"]) for p in played_calls}
    guards: dict[str, int] = {}
    for p in played_calls:
        for r in p["readings"]:
            for k, v in (r.get("guards") or {}).items():
                guards[k] = guards.get(k, 0) + v
    rows = [row for p in played_calls for row in agreement(p, labels)]
    confirmed = [r for r in rows if r["label"].get("confirmed")]
    return {
        "calls": len(played_calls), "readings": sum(len(p["readings"]) for p in played_calls),
        "points": sum(len(p["state"]["points"]) for p in played_calls),
        "latency": {
            "points_with_a_new_point_ms": {"n": len(points_ms), "p50": pct(points_ms, .5), "p90": pct(points_ms, .9), "max": max(points_ms, default=None)},
            "points_all_readings_ms": {"n": len(all_points_ms), "p50": pct(all_points_ms, .5), "p90": pct(all_points_ms, .9), "max": max(all_points_ms, default=None)},
            "progress_ms": {"n": len(progress_ms), "p50": pct(progress_ms, .5), "p90": pct(progress_ms, .9), "max": max(progress_ms, default=None)},
        },
        "errors": errors, "duplicates": {k: v for k, v in dup.items() if v}, "guards": guards,
        "invented": judged, "decision_rows": rows, "per_turn": per_turn(played_calls, labels),
        "agreement": {"labelled": len(rows), "agree": sum(r["ok"] for r in rows), "confirmed_labels": len(confirmed),
                      "confirmed_agree": sum(r["ok"] for r in confirmed)},
        "say_view": say_view_summary(played_calls, deepen_verdicts or []),
    }


def served_by(played_calls: list[dict]) -> dict[str, int]:
    """How many readings each provider wrote (the direct one first, OpenRouter only as its backup)."""
    out: dict[str, int] = {}
    for p in played_calls:
        for r in p["readings"]:
            if r.get("model"):
                out[r["model"].split(":")[0]] = out.get(r["model"].split(":")[0], 0) + 1
    return out


def render(summary: dict, played_calls: list[dict], *, details: bool, served: dict, date: str) -> str:
    """The report. Without `details` it holds numbers and ids only (it can be committed); with them it also quotes the
    customers' words and the lines the brain wrote (customer speech: keep it out of the repository)."""
    lat = summary["latency"]
    inv = summary["invented"]
    agree = summary["agreement"]
    pt = summary["per_turn"]

    def row(name: str, value: dict) -> str:
        return f"| {name} | {value['n']} | {value['p50']} | {value['p90']} | {value['max']} |"

    out = [
        f"# Live call assistant — eval report {date}" + ("" if details else " (numbers only)"),
        "",
        f"{summary['calls']} real calls, {summary['readings']} readings, {summary['points']} points. Model path: direct provider first, OpenRouter as its backup; "
        f"readings written by: {', '.join(f'{k} {v}' for k, v in sorted(served.items())) or '—'}.",
        "",
        "## Gates",
        "",
        "| Gate | Result | Bar |",
        "|---|---|---|",
        f"| Invented facts | {len(inv['number_flags'])} numbers + {len(inv['judge_flags'])} judge claims in {inv['lines']} lines (+{len(inv['example_lines'])} Ahora lines that are a playbook step's own sentence, listed apart) | 0 |",
        f"| Duplicate points | {sum(len(v) for v in summary['duplicates'].values())} pairs | 0 |",
        f"| Decisions vs labels | {agree['agree']}/{agree['labelled']} agree ({agree['confirmed_agree']}/{agree['confirmed_labels']} on labels a person confirmed) | agree with Dani's labels |",
        f"| Points latency, model time, readings that wrote a point | p90 {lat['points_with_a_new_point_ms']['p90']} ms | ≤ 1100 ms |",
        f"| Progress latency, model time | p90 {lat['progress_ms']['p90']} ms | ≤ 3000 ms |",
        f"| Reading errors | {len(summary['errors'])} | 0 |",
        "",
        "## One reply per prospect turn (order of work 1)",
        "",
        "| Measure | Result |",
        "|---|---|",
        f"| Turns with at least one point (the brain's decision) | {pt['turns_with_points']} |",
        f"| Points per turn that has something | {pt['points_per_turn_with_points']} (1: {pt['per_turn_distribution']['1']}, 2: {pt['per_turn_distribution']['2']}, 3+: {pt['per_turn_distribution']['3+']}) |",
        f"| End-of-turn readings that wrote a point | {pt['turn_end_readings_that_wrote']} of {pt['turn_end_readings']} |",
        f"| Labelled moments to handle that got a point | {pt['labels_need_with_point']} |",
        f"| Labelled moments with nothing to handle that got a point | {pt['labels_nothing_with_point']} |",
        f"| Results whose points are not in the order said | {pt['results_out_of_order']} |",
        f"| Answer length, words | p50 {pt['answer_words']['p50']} · p90 {pt['answer_words']['p90']} · max {pt['answer_words']['max']} (n {pt['answer_words']['n']}; over 20: {pt['answer_words']['over_20']}; over 2 sentences: {pt['answer_words']['over_2_sentences']}) |",
        "",
        "## The \"Qué decir\" view (build contract 2026-10-20 §2)",
        "",
        *say_view_lines(summary["say_view"]),
        "",
        "## Latency (ms, model time from the request to the end of the model's answer)",
        "",
        "| Reading | n | p50 | p90 | max |",
        "|---|---|---|---|---|",
        row("points that wrote a new point", lat["points_with_a_new_point_ms"]),
        row("points, every reading", lat["points_all_readings_ms"]),
        row("progress", lat["progress_ms"]),
        "",
        "## What the checks in code dropped or fixed",
        "",
        ", ".join(f"{k}: {v}" for k, v in sorted(summary["guards"].items())) or "nothing",
        "",
        "## Per call",
        "",
        "| Call | Type | Turns | Readings | Points (open / unanswered / promised) | Steps found | Data found | Goal | Provider |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for p in played_calls:
        pts = p["state"]["points"]
        count = lambda o: sum(1 for x in pts if x["outcome"] == o)  # noqa: E731
        prov = {}
        for r in p["readings"]:
            if r.get("model"):
                prov[r["model"].split(":")[0]] = prov.get(r["model"].split(":")[0], 0) + 1
        out.append(
            f"| {p['call']['id']} | {p['call']['motion']} | {len(p['call']['turns'])} | {len(p['readings'])} | {len(pts)} ({count('open')} / {count('unanswered')} / {count('promised')}) | "
            f"{len(p['state']['progress']['steps'])}/{p['ctx']['steps']} | {len(p['state']['progress']['data'])}/{p['ctx']['data']} | "
            f"{'yes' if p['state']['progress']['goal'] else 'no'} | {', '.join(f'{k} {v}' for k, v in prov.items())} |"
        )
    if details:
        out += ["", "## Invented-fact flags", ""]
        for flag in inv["number_flags"]:
            out.append(f"- {flag['call']} · {flag['kind']} · number {flag['number']} not in the sources or the call: «{flag['line']}»")
        for flag in inv["judge_flags"]:
            out.append(f"- {flag['call']} · {flag['kind']} · {'; '.join(flag['claims'])}: «{flag['line']}»")
        out += ["", "## Ahora lines that are a step's own example (a decision for Dani: an example can presume what the call has not shown)", ""]
        out += [f"- {x['call']}: «{x['line']}»" for x in inv["example_lines"]]
        out += ["", "## Decisions against labels", ""]
        for r in summary["decision_rows"]:
            mark = "✓" if r["ok"] else "✗"
            out.append(f"- {mark} {r['label']['call']} «{r['label']['said']}» — label {r['label']['expect']['decision']} · brain {r['got']}"
                       f"{' (' + r['title'] + ' → ' + (r['say'] or '') + ')' if r['title'] else ''}{'' if r['label'].get('confirmed') else ' [label not confirmed]'}")
        out += ["", "## Go deeper: every one, with the turn it came from and the judge's verdict", ""]
        for row in summary.get("deepen_rows") or []:
            out.append(f"- {row['call']} {row['turn']} [{row.get('verdict', '?')}] «{row['said']}» → «{row['question']}» (step {row['step']}, {row['outcome']})"
                       + (f" — {row['reason']}" if row.get("reason") else ""))
        out += ["", "## Responder with nothing to answer: next", ""]
        for p in played_calls:
            for r in p["readings"]:
                if r["producer"] == "points" and r["reason"] == "responder" and not r.get("new") and not r.get("updates"):
                    nxt = r.get("next")
                    out.append(f"- {p['call']['id']} {r['turn']}: " + (f"{nxt['label']} → «{nxt['question']}»" if nxt else "none"))
        out += ["", "## Rewrites", ""]
        for p in played_calls:
            shown_by_id = {pt["id"]: pt for pt in p["state"]["points"]}
            for a in p["asked"]["rewrite"]:
                pt = shown_by_id.get(a["target"]["point_id"], {})
                out.append(f"- {p['call']['id']} {pt.get('kind')} «{pt.get('title')}» v{a['target']['version'] + 1}: «{' / '.join(a['points'][0]['versions'])}» → "
                           f"{'«' + a['got']['answer'] + '»' if a['got'] else 'none'} ({a['model_ms']} ms)")
        out += ["", "## Step questions", ""]
        for p in played_calls:
            for a in p["asked"]["ask_step"]:
                out.append(f"- {p['call']['id']} at {a['turn']} {a['target']['kind']} {a['target']['id']}: {'«' + a['got']['question'] + '»' if a['got'] else 'none'} ({a['model_ms']} ms)")
        out += ["", "## Duplicate pairs", ""]
        for call, pairs in summary["duplicates"].items():
            title = {pt["id"]: pt["title"] for p in played_calls if p["call"]["id"] == call for pt in p["state"]["points"]}
            out += [f"- {call}: «{title.get(a)}» ~ «{title.get(b)}»" for a, b in pairs]
    return "\n".join(out) + "\n"


def say_view_lines(sv: dict) -> list[str]:
    d, nx, rw, st = sv["deepen"], sv["next"], sv["rewrite"], sv["ask_step"]
    verdicts = ", ".join(f"{k} {v}" for k, v in sorted(d["verdicts"].items())) or "not judged"

    def l(x: dict) -> str:
        return f"p50 {x['p50']} · p90 {x['p90']} · max {x['max']} (n {x['n']})"

    lines = [
        "| Measure | Result | Bar |",
        "|---|---|---|",
        f"| Go deeper: points written | {d['total']} in {d['turn_end_readings']} end-of-turn readings | does not fire on ordinary sentences |",
        f"| Go deeper per call | {', '.join(f'{k} {v}' for k, v in d['per_call'].items())} | |",
        f"| Go deeper, the judge's verdict on each trigger | {verdicts} | ordinary 0 |",
        f"| Go deeper dropped by the checks in code | {', '.join(f'{k} {v}' for k, v in sorted(d['guards'].items())) or 'none'} | |",
        f"| Responder with nothing to answer (no new point, none brought back) → next | {nx['with_next']} of {nx['with_nothing_to_answer']} (of {nx['responder_readings']} Responder readings) | |",
        f"| Rewrite: written / no other honest angle / errors | {rw['written']} / {rw['none']} / {rw['errors']} of {rw['n']} (a third version: {rw['second_written']} of {rw['second']}) | |",
        f"| Rewrite latency, model time | {l(rw['latency'])} | reported |",
        f"| Rewrite dropped by the checks in code | {', '.join(f'{k} {v}' for k, v in sorted(rw['guards'].items())) or 'none'} | |",
        f"| ask_step: questions written / errors | {st['written']} / {st['errors']} of {st['n']} | |",
        f"| ask_step latency, model time | {l(st['latency'])} | p90 ≤ 1100 ms |",
        f"| ask_step latency, whole request | {l(st['wall'])} | |",
        f"| ask_step checks in code | {', '.join(f'{k} {v}' for k, v in sorted(st['guards'].items())) or 'none'} | |",
    ]
    for call, info in sv["parts"].items():
        if info["steps_with_parts"]:
            lines.append(f"| Parts, {call} | steps with parts: {', '.join(info['steps_with_parts'])}; parts heard {info['parts_heard']}; done by parts: "
                         f"{', '.join(info['steps_done_by_parts']) or 'none'} | done only with evidence |")
    if not any(info["steps_with_parts"] for info in sv["parts"].values()):
        lines.append("| Parts | no published playbook of these calls has a step whose criterion lists parts | |")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--only", help="comma-separated call ids")
    parser.add_argument("--production-provider", action="store_true")
    parser.add_argument("--no-judge", action="store_true", help="skip the judge model (numbers are still checked)")
    parser.add_argument("--json", help="write every reading and the final states here (customer speech: keep it out of the repository)")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--no-say-view", action="store_true", help="read as the tabs view does (no go deeper)")
    parser.add_argument("--report", help="write the numbers-only report here (it can be committed)")
    parser.add_argument("--details", help="write the report with the customers' words and the brain's lines here (keep it out of the repository)")
    args = parser.parse_args()
    if args.production_provider:
        load_production_provider()
    sys.path.insert(0, str(HERE.parents[1]))
    from dotenv import load_dotenv

    load_dotenv(HERE.parents[1] / ".env")
    from app.services.copilot.suggest import live_direct

    if not live_direct():
        print("!! COPILOT_DIRECT_* is not set: the brain would go through OpenRouter, which production only uses as a fallback.\n"
              "!! Latency is NOT what reps get. Pass --production-provider.")
    wanted = set(args.only.split(",")) if args.only else None
    calls = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(CALLS.glob("*.local.json"))]
    calls = [c for c in calls if not wanted or c["id"] in wanted]
    labels = json.loads(LABELS.read_text(encoding="utf-8"))["labels"] if LABELS.exists() else []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        played = list(pool.map(lambda c: play(c, [l for l in labels if l["call"] == c["id"]], say_view=not args.no_say_view), calls))
    for p in played:
        print(f"{p['call']['id']}: {len(p['readings'])} readings, {len(p['state']['points'])} points, "
              f"{len(p['state']['progress']['steps'])} steps, {len(p['state']['progress']['data'])} data")
    judged: dict = {"lines": 0, "number_flags": [], "judge_flags": [], "example_lines": []}
    every = [(p, line) for p in played for line in lines_of(p)]
    judged["example_lines"] = [{"call": p["call"]["id"], "line": line["text"]} for p, line in every if line["from_example"]]
    work = [(p, line) for p, line in every if not line["from_example"]]
    judged["lines"] = len(work)
    for p, line in work:
        for n in numbers_invented(line, p):
            judged["number_flags"].append({"call": p["call"]["id"], "kind": line["kind"], "number": n, "line": line["text"]})
    if not args.no_judge:
        with ThreadPoolExecutor(max_workers=8) as pool:
            for (p, line), found in zip(work, pool.map(lambda w: judge(w[1], w[0]), work)):
                if found:
                    judged["judge_flags"].append({"call": p["call"]["id"], "kind": line["kind"], "claims": found, "line": line["text"]})
    rows = [(p, row) for p in played for row in deepen_rows(p)]
    verdicts = []
    if not args.no_judge and rows:
        with ThreadPoolExecutor(max_workers=8) as pool:
            verdicts = list(pool.map(lambda w: judge_deepen(w[1], w[0]), rows))
    for (_p, row), verdict in zip(rows, verdicts):
        row.update(verdict)
    summary = summarise(played, labels, judged, verdicts)
    summary["deepen_rows"] = [row for _p, row in rows]
    print(json.dumps({k: v for k, v in summary.items() if k not in ("decision_rows", "deepen_rows")}, ensure_ascii=False, indent=1))
    if args.json:
        Path(args.json).write_text(json.dumps({"summary": summary, "played": [
            {"id": p["call"]["id"], "state": p["state"], "readings": p["readings"], "recaps": p["recaps"], "asked": p["asked"], "heard": p["heard"],
             "ctx": {k: v for k, v in p["ctx"].items() if k != "sources"}}
            for p in played]}, ensure_ascii=False, indent=1), encoding="utf-8")
    from datetime import date

    served = served_by(played)
    for path, with_details in ((args.report, False), (args.details, True)):
        if path:
            Path(path).write_text(render(summary, played, details=with_details, served=served, date=date.today().isoformat()), encoding="utf-8")
    bad = bool(summary["errors"] or summary["duplicates"] or judged["number_flags"] or judged["judge_flags"])
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
