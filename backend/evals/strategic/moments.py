"""Same moment, same memory, different model or reasoning: what does each decide?

    cd backend && PATH=$HOME/.railway/bin:$PATH python -m evals.strategic.moments --moments m.json --state v2b.json --out out.json

m.json: [{"id": "A1", "call": "5c013cf3", "upto": "t22", "ideal": "..."}]. The memory at each moment is rebuilt from a v2 run
(`--state`): the quotes kept before it, the previous reading's conclusions and open opportunities, the cards already shown.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from evals.strategic import run_v2
from evals.strategic.run import CALLS, context_for, ends, finished_by

FLASH = "deepseek-ai/DeepSeek-V4.1-Flash-1017"
CONFIGS = {f"flash-{effort}": (FLASH, effort) for effort in ("none", "low", "high", "xhigh", "max")}
PRICES = {FLASH: (0.30, 0.006, 1.20)}  # $ per million: input, cached input, output


def moment_input(call: dict, played: dict, sources: str, upto_id: str) -> str:
    turns = call["turns"]
    end = ends(turns)
    idx = next(i for i, t in enumerate(turns) if t["id"] == upto_id)
    now = end[idx]
    upto = finished_by(end, now)
    before = [r for r in played["readings"] if r["upto"] <= upto and r["output"]]
    prev = before[-1]["output"] if before else None
    seen = {t["id"] for t in turns[:upto]}
    memory = {
        "observations": [o for o in played["observations"] if o["turn"] in seen],
        "previous": {k: prev.get(k) for k in ("purpose", "asked_and_answered", "conclusions")} if prev else None,
        "open": [{**o, "age_s": 0} for o in (prev or {}).get("open_opportunities") or []],
        "opened": {},
    }
    shown = [s for s in played["shown"] if s["visible_t"] <= now]
    return run_v2.reading_input(sources, turns, upto, run_v2.measured(turns, upto, end, now), memory, shown)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--moments", required=True)
    parser.add_argument("--state", required=True, help="a run_v2 output whose memory is reused")
    parser.add_argument("--configs", default=",".join(CONFIGS))
    parser.add_argument("--repeat", type=int, default=2)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from evals.copilot.run import load_production_provider

    load_production_provider()
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    moments = json.loads(Path(args.moments).read_text(encoding="utf-8"))
    played = {p["id"]: p for p in json.loads(Path(args.state).read_text(encoding="utf-8"))["played"]}
    calls = {c: json.loads((CALLS / f"{c}.local.json").read_text(encoding="utf-8")) for c in {m["call"] for m in moments}}
    sources = {c: context_for(call) for c, call in calls.items()}
    inputs = {m["id"]: moment_input(calls[m["call"]], played[m["call"]], sources[m["call"]], m["upto"]) for m in moments}

    def one(job):
        m, name, k = job
        model, effort = CONFIGS[name]
        run_v2.MODEL = model  # read by run_v2.ask
        out = run_v2.ask(run_v2.SYSTEM, inputs[m["id"]], effort, 2000 + (0 if effort == "none" else 16000), run_v2.SCHEMA,
                         f"moments-{m['id']}-{name}")
        price = PRICES[model]
        cost = ((out["prompt_tokens"] - out["cached_tokens"]) * price[0] + out["cached_tokens"] * price[1] + out["completion_tokens"] * price[2]) / 1e6
        d = (out["parsed"] or {}).get("decision") or {}
        return {"moment": m["id"], "config": name, "run": k, "latency": round(out["latency"], 1), "cost": cost, "error": out["error"],
                "reasoning_tokens": out["reasoning_tokens"], "act": d.get("act"), "about": d.get("about"), "action": d.get("action"),
                "say": d.get("say"), "what_changed": d.get("what_changed"), "basis": d.get("basis")}

    jobs = [(m, name, k) for m in moments for name in args.configs.split(",") for k in range(args.repeat)]
    # One model per worker batch: run_v2.MODEL is module state, so configs run one after another, moments in parallel.
    rows = []
    for name in args.configs.split(","):
        with ThreadPoolExecutor(max_workers=8) as pool:
            rows += list(pool.map(one, [j for j in jobs if j[1] == name]))
    Path(args.out).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    for name in args.configs.split(","):
        rs = [r for r in rows if r["config"] == name and not r["error"]]
        lat = sorted(r["latency"] for r in rs)
        print(f"{name}: {len(rs)} answers, latency p50 {lat[len(lat) // 2] if lat else 0}s, max {lat[-1] if lat else 0}s, "
              f"cost per reading ${sum(r['cost'] for r in rs) / max(1, len(rs)):.4f}, intervene {sum(r['act'] == 'intervene' for r in rs)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
