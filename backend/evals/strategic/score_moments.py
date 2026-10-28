"""Score a v2 run against the reference moments Dani validated (no AI judge deciding what matters).

    cd backend && PATH=$HOME/.railway/bin:$PATH python -m evals.strategic.score_moments RUN.json [RUN2.json ...] --out scores.json

Moments (evals/copilot/calls/momentos-referencia.local.json, gitignored): each has a call, a window of turns and Dani's
label: "critico" / "intervenir" (a card with that intent should appear while the rep can still use it), "preferido"
(welcome, no penalty for silence), "opcional" (card or silence both fine, unless the card is bad) and "silencio" (any
card is noise). A card's intent is checked against the moment by a cheap model call; everything else is counted by code.
Cards outside every moment are listed for review.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from evals.strategic import run_v2
from evals.strategic.run import CALLS, ends

MOMENTS = CALLS / "momentos-referencia.local.json"
GRACE_TURNS, LATE_TURNS = 2, 6

MATCH_SYSTEM = """You check ONE card a live sales assistant showed against a reference moment that a head of sales labelled.
Given the moment (what is happening, the help expected, valid examples, what would be bad, the head of sales' note), the
latest conversation and the card, answer JSON:
{"verdict": "matches" (the card asks for essentially the expected help; wording can differ) | "fine" (a different but
reasonable card, not what was expected) | "bad" (what the moment says would be bad, or it would hurt or distract here),
"sayable": true if, seeing it for one second while listening, the rep knows exactly what to say or do (a natural line
they could say as is, or a very short instruction); false if it is vague, long, a menu or needs thinking,
"quality": the card's CONTENT judged on its own, as if the rep had needed help here: "right" (true to the conversation,
claims nothing unsupported, consistent with the company's approach) | "wrong" (invents or misstates a fact, misreads
what they said, or would harm the conversation) — a correct card the rep did not need is still "right",
"why": at most 12 words}"""
MATCH_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["verdict", "sayable", "quality", "why"],
                "properties": {"verdict": {"type": "string", "enum": ["matches", "fine", "bad"]}, "sayable": {"type": "boolean"},
                               "quality": {"type": "string", "enum": ["right", "wrong"]}, "why": {"type": "string"}}}


def card_text(s: dict) -> str:
    """What the rep saw: the line (older runs also had a title, kept in brackets)."""
    if "source_quote" in s:
        return f"«{s['say']}»"
    return f"[{s['kind']}] «{s['say']}»" if s.get("say") else f"[{s['kind']}]"


def check(moment: dict, card: dict, turns: list[dict], upto: int) -> dict:
    convo = "\n".join(f"{'Them' if t['who'] == 'them' else 'Rep'}: {' '.join(t['text'].split())}" for t in turns[max(0, upto - 10):upto])
    user = (f"MOMENT ({moment['dani']}): {moment['what']}\nEXPECTED: {moment['expected'] or 'no card'}\nVALID EXAMPLES: {moment['accepted'] or '-'}\n"
            f"WOULD BE BAD: {moment['bad'] or '-'}\nHEAD OF SALES NOTE: {moment.get('dani_note') or '-'}\n\nCONVERSATION (latest):\n{convo}\n\n"
            f"THE CARD: {card_text(card)}")
    out = run_v2.ask(MATCH_SYSTEM, user, "none", 120, MATCH_SCHEMA, f"score-{moment['id']}")
    return out["parsed"] or {"verdict": "fine", "sayable": False, "quality": "right", "why": "check failed"}


def score(run: dict, moments: list[dict]) -> dict:
    by_call: dict[str, list[dict]] = {}
    for m in moments:
        by_call.setdefault(m["call"], []).append(m)
    rows, unlabelled, jobs = [], [], []
    for cid, ms in by_call.items():
        played = run.get(cid)
        if not played:
            continue
        turns = json.loads((CALLS / f"{cid}.local.json").read_text(encoding="utf-8"))["turns"]
        end = ends(turns)
        idx = {t["id"]: i for i, t in enumerate(turns)}
        cards = played["shown"]
        used = set()
        for m in ms:
            lo, hi = idx[m["from"]], idx[m["to"]]
            start, stop = turns[lo]["t"], end[min(len(turns) - 1, hi + GRACE_TURNS)]
            late_stop = end[min(len(turns) - 1, hi + LATE_TURNS)]
            inside = [k for k, s in enumerate(cards) if start <= s["visible_t"] <= stop]
            later = [k for k, s in enumerate(cards) if stop < s["visible_t"] <= late_stop]
            used.update(inside)
            row = {"moment": m["id"], "call": cid, "label": m["dani"], "inside": inside, "later": later, "checks": {}}
            rows.append(row)
            for k in (inside + later if m["dani"] in ("critico", "intervenir", "preferido") else inside):
                upto = sum(1 for e in end if e <= cards[k]["visible_t"] + 1e-6)
                jobs.append((row, k, m, cards[k], turns, upto))
        unlabelled += [{"call": cid, "at": round(s["visible_t"]), "card": card_text(s)} for k, s in enumerate(cards) if k not in used]
    with ThreadPoolExecutor(max_workers=8) as pool:
        for (row, k, m, card, turns, upto), out in zip(jobs, pool.map(lambda j: check(j[2], j[3], j[4], j[5]), jobs)):
            row["checks"][k] = {**out, "card": card_text(card)}
    for row in rows:
        v = lambda ks: [row["checks"][k]["verdict"] for k in ks if k in row["checks"]]
        # A hit is the expected help AND something the rep can use at a glance.
        good = lambda ks: any(row["checks"][k]["verdict"] == "matches" and row["checks"][k].get("sayable") for k in ks if k in row["checks"])
        if row["label"] in ("critico", "intervenir", "preferido"):
            row["result"] = ("hit" if good(row["inside"]) else "late" if good(row["later"])
                             else "wrong_card" if row["inside"] else "miss")
        elif row["label"] == "silencio":
            row["result"] = "noise" if row["inside"] else "ok"
        else:
            row["result"] = "bad" if "bad" in v(row["inside"]) else "ok"
    return {"rows": rows, "unlabelled": unlabelled}


def summary(result: dict, run: dict) -> dict:
    rows = result["rows"]
    count = lambda label, res: sum(1 for r in rows if r["label"] in label and r["result"] == res)
    total = lambda label: sum(1 for r in rows if r["label"] in label)
    must = ("critico", "intervenir")
    minutes = sum(p["duration"] for p in run.values()) / 60
    cost = sum(p["cost"] for p in run.values())
    cards = sum(len(p["shown"]) for p in run.values())
    # Need and quality apart: a card in a silence moment is noise whatever its content; its content can still be right.
    noise_checks = [c for r in rows if r["label"] == "silencio" for c in r["checks"].values()]
    checked = [c for r in rows for c in r["checks"].values()]
    return {"must_hit": f"{count(must, 'hit')}/{total(must)}", "must_late": count(must, "late"), "must_wrong_card": count(must, "wrong_card"),
            "must_miss": count(must, "miss"), "critical_hit": f"{count(('critico',), 'hit')}/{total(('critico',))}",
            "preferred_hit": f"{count(('preferido',), 'hit')}/{total(('preferido',))}",
            "silence_noise": f"{count(('silencio',), 'noise')}/{total(('silencio',))}",
            "noise_cards_right_content": sum(1 for c in noise_checks if c.get("quality") == "right"),
            "noise_cards_wrong_content": sum(1 for c in noise_checks if c.get("quality") == "wrong"),
            "checked_cards_wrong_content": f"{sum(1 for c in checked if c.get('quality') == 'wrong')}/{len(checked)}",
            "optional_bad": count(("opcional",), "bad"),
            "unlabelled_cards": len(result["unlabelled"]), "cards_per_10_min": round(10 * cards / max(1e-9, minutes), 1),
            "cost_per_30_min": round(30 * cost / max(1e-9, minutes), 3)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("runs", nargs="+")
    parser.add_argument("--out")
    parser.add_argument("--moments", default=str(MOMENTS), help="the labelled moments (default: the validated ones)")
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from evals.copilot.run import load_production_provider

    load_production_provider()
    moments = json.loads(Path(args.moments).read_text(encoding="utf-8"))
    report = {}
    for path in args.runs:
        run = {p["id"]: p for p in json.loads(Path(path).read_text(encoding="utf-8"))["played"]}
        run = {cid: p for cid, p in run.items() if any(m["call"] == cid for m in moments)}
        result = score(run, moments)
        report[path] = {"summary": summary(result, run), **result}
        print(Path(path).name, json.dumps(report[path]["summary"], ensure_ascii=False))
    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
