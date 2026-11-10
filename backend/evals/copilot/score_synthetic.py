"""Score a live_brain_run of synthetic calls (synthetic_calls.py) against what each call's scenario meant.

    cd backend && python -m evals.copilot.score_synthetic --run /tmp/run.json --prefix syn-movertis --out /tmp/report.md

For every prospect turn the scenario marked (`expected`): did the brain show a card for it, was it the playbook answer the
scenario meant, and what did it say. For every other prospect turn: a card there is an extra (on a call with no objection it
is an interruption). The expected turns are the scenario model's intention, not a person's label: read the lines, not only
the numbers.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from evals.copilot.live_brain_run import MIN_PROSPECT_WORDS, words

CALLS = Path(__file__).with_name("calls")


def _shown(point: dict) -> str:
    return point.get("answer") or point.get("fallback") or ""


def _source(point: dict) -> str | None:
    source = point.get("source")
    return source.get("id") if isinstance(source, dict) else None


def score_call(call: dict, played: dict) -> dict:
    turns = {t["id"]: t for t in call["turns"]}
    cards = [p for r in played["readings"] if r["producer"] == "points" for p in r.get("new") or []]
    second = sum((r.get("guards") or {}).get("second_look", 0) for r in played["readings"])
    by_turn: dict[str, list[dict]] = {}
    for card in cards:
        for tid in card.get("turn_ids") or []:
            by_turn.setdefault(tid, []).append(card)
    rows, expected_ids = [], set()
    order = [t["id"] for t in call["turns"]]
    for want in call.get("expected") or []:
        tid = want["turn"]
        # The writing model sometimes numbers one turn off and points at the rep's line: take the prospect's line before it.
        if turns[tid]["who"] != "them":
            before = [i for i in order[: order.index(tid)] if turns[i]["who"] == "them"]
            if not before:
                continue
            tid = before[-1]
        expected_ids.add(tid)
        got = by_turn.get(tid) or []
        entry = want.get("entry_id")
        right = [c for c in got if entry and entry in (c.get("tag_key"), _source(c))]
        too_short = words(turns[tid]["text"]) < MIN_PROSPECT_WORDS
        status = "right" if right else ("card" if got else ("not_read" if too_short else "missed"))
        if not entry and got:
            status = "card"
        rows.append({"turn": tid, "said": turns[tid]["text"], "want": want, "status": status, "cards": right or got})
    extras = [
        {"turn": tid, "said": turns[tid]["text"], "cards": got}
        for tid, got in by_turn.items() if tid not in expected_ids and turns.get(tid, {}).get("who") == "them"
    ]
    return {"id": call["id"], "scenario": call["scenario"], "rows": rows, "extras": extras, "cards": len(cards), "second_looks": second}


def render(scored: list[dict]) -> str:
    rows = [r for s in scored for r in s["rows"]]
    by_status = Counter(r["status"] for r in rows)
    want_entry = [r for r in rows if r["want"].get("entry_id")]
    quiet = [s for s in scored if s["scenario"]["kind"] in ("positive", "trap")]
    lines = [
        "# Synthetic calls through the live brain", "",
        f"{len(scored)} calls, {len(rows)} moments the scenario meant as an objection, a question or a pain to dig into.", "",
        "| | moments |", "|---|---|",
        f"| card with the playbook answer meant | {sum(1 for r in want_entry if r['status'] == 'right')} of {len(want_entry)} |",
        f"| a card, but not that answer (or no answer meant) | {by_status['card']} |",
        f"| no card | {by_status['missed']} |",
        f"| never read (under {MIN_PROSPECT_WORDS} words, the island skips it) | {by_status['not_read']} |",
        f"| extra cards on other turns | {sum(len(s['extras']) for s in scored)} |",
        f"| extra cards on calls with no objection ({len(quiet)} calls) | {sum(len(s['extras']) for s in quiet)} |",
        f"| second looks that found a card | {sum(s['second_looks'] for s in scored)} |", "",
    ]
    kinds = Counter((s["scenario"]["kind"], r["status"]) for s in scored for r in s["rows"])
    lines += ["By scenario kind (right / other card / no card / not read):", ""]
    for kind in sorted({s["scenario"]["kind"] for s in scored}):
        lines.append(f"- {kind}: {kinds[(kind, 'right')]} / {kinds[(kind, 'card')]} / {kinds[(kind, 'missed')]} / {kinds[(kind, 'not_read')]}")
    lines.append("")
    for s in scored:
        sc = s["scenario"]
        lines.append(f"## {s['id']} · {sc['kind']} · {sc['name']}")
        for r in s["rows"]:
            mark = {"right": "✅", "card": "🟡", "missed": "❌", "not_read": "⚪"}[r["status"]]
            lines.append(f"- {mark} [{r['turn']}] «{r['said']}» — meant: {r['want'].get('kind')} {r['want'].get('entry_id') or ''}")
            for c in r["cards"]:
                lines.append(f"    - card ({c.get('tag_key')}, source {_source(c) or 'none'}): «{_shown(c)}»")
        for e in s["extras"]:
            for c in e["cards"]:
                lines.append(f"- ➕ extra [{e['turn']}] «{e['said']}» → ({c.get('tag_key')}, source {_source(c) or 'none'}): «{_shown(c)}»")
        if not s["rows"] and not s["extras"]:
            lines.append("- no card, none meant ✅")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--run", required=True, help="the --json file of live_brain_run")
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    played = {p["id"]: p for p in json.loads(Path(args.run).read_text(encoding="utf-8"))["played"]}
    calls = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(CALLS.glob(f"{args.prefix}-*.local.json"))]
    scored = [score_call(c, played[c["id"]]) for c in calls if c["id"] in played]
    Path(args.out).write_text(render(scored), encoding="utf-8")
    print(render(scored).split("\n\nBy scenario")[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
