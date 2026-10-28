"""Judge each card with only what was known when it appeared: no hindsight about what the rep said afterwards.

    python -m evals.strategic.judge_moment build --runs B-v30.json,B-v31.json --out DIR     # blinded packets per call
    (a judge writes DIR/verdict-<call>.json: [{"id", "valid", "needed", "harmful", "why"}])
    python -m evals.strategic.judge_moment score --runs B-v30.json,B-v31.json --dir DIR

A card cannot know what the rep will say next, so it is judged on the conversation up to the moment it appears and the
company's context: is it right (true, consistent with the playbook), would the rep likely miss something that matters
without it, and could it hurt. Cards from several runs are merged and shuffled, so the judge does not know which version
wrote which.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from evals.strategic.run import CALLS, SECONDS_PER_WORD, ends

PAST_TURNS = 25


def past(turns: list[dict], at: float) -> str:
    """The conversation as it stood at second `at`: finished turns, and the words of a turn still in progress so far."""
    end = ends(turns)
    lines = []
    for i, t in enumerate(turns):
        if t["t"] > at:
            break
        text = " ".join(t["text"].split())
        if end[i] > at:
            text = " ".join(text.split()[: max(1, int((at - t["t"]) / SECONDS_PER_WORD))]) + " …"
        lines.append(f"({int(t['t'] // 60)}:{int(t['t'] % 60):02d}) {'Cliente' if t['who'] == 'them' else 'Comercial'}: {text}")
    return "\n".join(lines[-PAST_TURNS:])


def build(runs: list[str], out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    played = [{p["id"]: p for p in json.loads(Path(r).read_text(encoding="utf-8"))["played"]} for r in runs]
    random.seed(41)
    key = {}
    for cid in played[0]:
        turns = json.loads((CALLS / f"{cid}.local.json").read_text(encoding="utf-8"))["turns"]
        cards = []
        for k, run in enumerate(played):
            for n, s in enumerate(run[cid]["shown"]):
                cards.append({"run": k, "index": n, "at": s["visible_t"], "say": s["say"]})
        random.shuffle(cards)
        packet = []
        for j, c in enumerate(sorted(cards, key=lambda c: c["at"])):
            cid_card = f"{cid}-{j}"
            key[cid_card] = {"run": c["run"], "index": c["index"]}
            packet.append({"id": cid_card, "at": f"{int(c['at'] // 60)}:{int(c['at'] % 60):02d}", "card": c["say"],
                           "conversation_until_card": past(turns, c["at"])})
        (out / f"packet-{cid}.json").write_text(json.dumps(packet, ensure_ascii=False, indent=1), encoding="utf-8")
        print(cid, len(packet), "cards")
    (out / "key.json").write_text(json.dumps(key, indent=1), encoding="utf-8")


def score(runs: list[str], out: Path) -> None:
    key = json.loads((out / "key.json").read_text(encoding="utf-8"))
    played = [{p["id"]: p for p in json.loads(Path(r).read_text(encoding="utf-8"))["played"]} for r in runs]
    minutes = sum(p["duration"] for p in played[0].values()) / 60
    tot = [{"cards": 0, "needed": 0, "not_needed": 0, "invalid": 0, "harmful": 0} for _ in runs]
    for path in sorted(out.glob("verdict-*.json")):
        for v in json.loads(path.read_text(encoding="utf-8")):
            t = tot[key[v["id"]]["run"]]
            t["cards"] += 1
            t["needed" if v["needed"] and v["valid"] and not v["harmful"] else "not_needed"] += 1
            t["invalid"] += not v["valid"]
            t["harmful"] += bool(v["harmful"])
    for r, t in zip(runs, tot):
        print(f"{Path(r).name}: {t['cards']} cards ({10 * t['cards'] / minutes:.1f}/10 min); needed and right {t['needed']}, "
              f"not needed {t['not_needed']}, wrong {t['invalid']}, harmful {t['harmful']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("action", choices=["build", "score"])
    parser.add_argument("--runs", required=True)
    parser.add_argument("--dir", "--out", dest="dir", required=True)
    args = parser.parse_args()
    (build if args.action == "build" else score)(args.runs.split(","), Path(args.dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
