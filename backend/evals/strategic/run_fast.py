"""The fast assistant (production's /live/points and /live/progress, read as of each call's day) replayed on semantic turns.

    cd backend && PATH=$HOME/.railway/bin:$PATH python -m evals.strategic.run_fast --out fast.json

Same producers, prompts and model as production (Together direct, reasoning none; refuses to run otherwise). What changes
from evals/copilot/live_brain_run is only WHEN they read, as turns.py defines it:
- the other side finished an idea (their pause with a complete thought, by production's turn check, or the rep really
  took the floor), with at least MIN_WORDS new words: points and progress, as production's turn_end;
- a pause mid-idea: points only, once LONG_TURN_S has passed since the last points reading (production's long_turn);
- the rep said REP_WORDS new words of substance (a «claro» or «sí, eso es» is listening, not a reply), REP_GAP_S
  after the last reading: progress, and points if a point is open (production's rep_turn).
No Responder taps: only what appears on its own.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from evals.copilot import live_brain_run as lb
from evals.strategic import turns as semantic
from evals.strategic.run import CALLS, ends

MIN_WORDS, LONG_TURN_S, REP_WORDS, REP_GAP_S = 4, 15.0, 8, 6.0


def play(call: dict) -> dict:
    client, sb, membership, api = lb.client_for(call)
    from app.services.copilot.live_models import LiveReading

    turns = call["turns"]
    end = ends(turns)
    finished = semantic.turn_checks(call)
    stub = LiveReading(call_id=call["id"], sales_motion_key=call["motion"], call_mode=call["call_mode"], turns=turns[:1])
    ctx = asyncio.run(api._brain_context(sb, membership, stub))
    base = {"call_id": call["id"], "sales_motion_key": call["motion"], "call_mode": call["call_mode"], "language": "es", "say_view": True}
    state = lb.js("empty", call_id=call["id"])
    readings: list[dict] = []
    covered = -1

    def reading(idx: int, producer: str, reason: str, focus: int | None = None):
        nonlocal state
        upto = turns[: idx + 1]
        body = {**base, "reason": reason, "turns": lb.window_of(upto), "state_version": state["version"], "type_changed": False,
                "cursor": state["cursors"]["points" if producer == "points" else "progress"],
                "points": lb.js("pointsIn", state), "progress": lb.js("progressIn", state),
                **({"focus_from": upto[focus]["id"]} if focus is not None else {})}
        response = client.post(f"/api/v1/copilot/live/{producer}", json=body)
        entry = {"turn": upto[-1]["id"], "idx": idx, "producer": producer, "reason": reason, "error": None}
        if response.status_code != 200:
            entry["error"] = f"HTTP {response.status_code}"
            readings.append(entry)
            return
        if producer == "points":
            frames = lb.sse_frames(response.text)
            result = next((f for f in reversed(frames) if f["type"] == "result"), None)
            if result:
                entry.update(model_ms=result.get("latency_ms"), model=result.get("model"), guards=result.get("guards") or {},
                             new=[p for p in result["points"] if not p.get("is_update")], closed=result["closed"])
                state = lb.js("applyPoints", state, result, asked=False)
        else:
            result = response.json()
            entry.update(model_ms=result.get("latency_ms"), model=result.get("model"))
            state = lb.js("applyProgress", state, result)
        readings.append(entry)

    signals = semantic.listening(turns)
    ideas = set(semantic.idea_ends(turns, finished))
    last_points_t, rep_read = -1e9, {"words": 0, "t": -1e9}
    rep_total = 0
    for i, t in enumerate(turns):
        if i in signals:
            continue
        if t["who"] == "them":
            fresh = sum(len(semantic.tokens(u["text"])) for u in turns[covered + 1:i + 1] if u["who"] == "them")
            if fresh < MIN_WORDS:
                continue
            if i in ideas:
                reading(i, "points", "turn_end", focus=max(0, covered))
                reading(i, "progress", "turn_end")
                covered, last_points_t = i, end[i]
                rep_read = {"words": rep_total, "t": end[i]}
            elif end[i] - last_points_t >= LONG_TURN_S:
                reading(i, "points", "long_turn", focus=max(0, covered))
                covered, last_points_t = i, end[i]
        else:
            rep_total += semantic.substance(t["text"])
            if rep_total - rep_read["words"] >= REP_WORDS and end[i] - rep_read["t"] >= REP_GAP_S:
                rep_read = {"words": rep_total, "t": end[i]}
                reading(i, "progress", "rep_turn")
                if any(p["outcome"] in ("open", "unanswered") for p in state["points"]):
                    reading(i, "points", "rep_turn", focus=max(0, covered))
    return {"id": call["id"], "state": state, "readings": readings, "ctx": {"version": ctx.playbook_version_id}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--only", required=True, help="comma-separated call ids")
    parser.add_argument("--out", required=True)
    parser.add_argument("--workers", type=int, default=5)
    args = parser.parse_args()
    lb.load_production_provider()
    sys.path.insert(0, str(lb.HERE.parents[1]))
    from dotenv import load_dotenv

    load_dotenv(lb.HERE.parents[1] / ".env")
    from app.api import copilot as copilot_api
    from app.services.copilot.suggest import live_direct
    from evals.strategic.history import install, reliable_reads

    direct = live_direct()
    if not direct or "together" not in direct[0]:
        sys.exit("the direct provider (Together) is not configured in this process: refusing to run")
    calls = [json.loads((CALLS / f"{c}.local.json").read_text(encoding="utf-8")) for c in args.only.split(",")]
    install(copilot_api, calls)
    reliable_reads()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        played = list(pool.map(play, calls))
    Path(args.out).write_text(json.dumps({"played": played}, ensure_ascii=False, indent=1), encoding="utf-8")
    for p in played:
        pts = [r for r in p["readings"] if r["producer"] == "points"]
        print(f"{p['id']}: {len(pts)} points readings, {sum(len(r.get('new') or []) for r in pts)} new points, "
              f"{sum(1 for r in p['readings'] if r['error'])} errors")
    return 0


if __name__ == "__main__":
    sys.exit(main())
