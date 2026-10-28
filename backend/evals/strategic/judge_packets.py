"""Blind judge packets and the unblinded score for the strategic-brain experiment.

    python -m evals.strategic.judge_packets build --runs DIR --set dev      # writes DIR/exp/judge-in-<call>.json + key
    python -m evals.strategic.judge_packets score --runs DIR --set dev      # reads DIR/exp/verdict-<call>.json

Per call, what each configuration put on the rep's screen, labelled at random, plus the fast cards (common to all).
Run files expected in DIR: a-all.json + a-new.json (current system), v2b.json + v2b-new.json, v2c.json + v2c-new.json.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from evals.strategic.run import CALLS, ends, finished_by

SETS = {
    "dev": ["816ba4f7", "5c013cf3", "proto", "0a187842", "281116db", "9bdfe6bd"],
    "holdout": ["916d1bd8", "9f125ca1", "6a554f16", "129c6308", "ca17533a", "0f2687bc", "ad11a03e", "e2c3fe40", "80bd8aac", "83411b6f"],
}
CURRENT = ["a-all.json", "a-new.json"]
STRATEGIC = {"v2B": ["v2b.json", "v2b-new.json"], "v2C": ["v2c.json", "v2c-new.json"]}
WINDOWS = ["windows-dev.json", "windows-holdout.json", "windows-new.json"]
NAMES = {"A": "Current system", "v2B": "v2, no reasoning", "v2C": "v2, reasoning high", "fast": "Fast cards (common)"}


def load(runs: Path, files: list[str]) -> dict:
    """Played calls by id; a later file wins for a call it also has."""
    out = {}
    for f in files:
        if (runs / f).exists():
            out.update({p["id"]: p for p in json.loads((runs / f).read_text(encoding="utf-8"))["played"]})
    return out


def current_items(played: dict, turns: list[dict]) -> tuple[list[dict], list[dict]]:
    """The current system's fast cards and its «now» line, each when it would have appeared."""
    end = ends(turns)
    fast, now, last = [], [], None
    for r in played["readings"]:
        ready = end[r["idx"]] + (r.get("model_ms") or 0) / 1000
        after = turns[max(0, finished_by(end, ready) - 1)]["id"]
        if r["producer"] == "points":
            for p in r.get("new") or []:
                text = p.get("answer") or p.get("fallback")
                if text:
                    fast.append({"after_turn": after, "t": round(ready, 1), "text": text})
        elif (r.get("now") or {}).get("say") and r["now"]["say"] != last:
            last = r["now"]["say"]
            now.append({"after_turn": after, "t": round(ready, 1), "text": last})
    return fast, now


def build(runs: Path, which: str) -> None:
    current = load(runs, CURRENT)
    strategic = {name: load(runs, files) for name, files in STRATEGIC.items()}
    windows = {}
    for f in WINDOWS:
        if (runs / "exp" / f).exists():
            windows.update(json.loads((runs / "exp" / f).read_text(encoding="utf-8")))
    random.seed(23)
    key = {}
    for cid in SETS[which]:
        turns = json.loads((CALLS / f"{cid}.local.json").read_text(encoding="utf-8"))["turns"]
        fast, now = current_items(current[cid], turns)
        shown = {"A": now}
        for name, played in strategic.items():
            if cid in played:
                shown[name] = [{"after_turn": s["after_turn"], "t": round(s["visible_t"], 1),
                                "text": f"{s['action']} — «{s['say']}»" if s["say"] else s["action"]} for s in played[cid]["shown"]]
        labels = ["X", "Y", "Z"][-len(shown):]
        random.shuffle(labels)
        key[cid] = dict(zip(shown, labels))
        packet = {"windows": windows[cid], "shown": {"fast": fast, **{key[cid][n]: items for n, items in shown.items()}}}
        (runs / "exp" / f"judge-in-{cid}.json").write_text(json.dumps(packet, ensure_ascii=False, indent=1), encoding="utf-8")
        print(cid, {n: len(v) for n, v in shown.items()}, "fast", len(fast))
    (runs / "exp" / f"key-{which}.json").write_text(json.dumps(key, indent=1), encoding="utf-8")


def score(runs: Path, which: str) -> None:
    key = json.loads((runs / "exp" / f"key-{which}.json").read_text(encoding="utf-8"))
    tot: dict = {}
    minutes = 0.0
    for cid in SETS[which]:
        path = runs / "exp" / f"verdict-{cid}.json"
        if not path.exists():
            print("missing verdict", cid)
            continue
        turns = json.loads((CALLS / f"{cid}.local.json").read_text(encoding="utf-8"))["turns"]
        minutes += ends(turns)[-1] / 60
        v = json.loads(path.read_text(encoding="utf-8"))
        inv = {label: name for name, label in key[cid].items()} | {"fast": "fast"}
        for it in v["items"]:
            t = tot.setdefault(inv[it["config"]], {"shown": 0, "useful": 0, "late": 0, "unnecessary": 0, "harmful": 0,
                                                    "invented": 0, "outside_harmful": 0, "windows": 0, "windows_total": 0, "best": 0})
            t["shown"] += 1
            t[it["verdict"]] = t.get(it["verdict"], 0) + 1
            t["invented"] += it.get("invented") not in (None, False, "none")
            t["outside_harmful"] += it["verdict"] == "harmful" and not it.get("window")
        for w in v["windows"]:
            for label in key[cid].values():
                t = tot.setdefault(inv[label], {"shown": 0, "useful": 0, "late": 0, "unnecessary": 0, "harmful": 0,
                                                "invented": 0, "outside_harmful": 0, "windows": 0, "windows_total": 0, "best": 0})
                t["windows_total"] += 1
                t["windows"] += bool(w.get(label))
        best = v.get("summary", {}).get("best")
        if best in inv:
            tot[inv[best]]["best"] += 1
    print(f"{which}: {minutes:.0f} minutes of calls")
    for name in ("A", "v2B", "v2C", "fast"):
        t = tot.get(name)
        if not t:
            continue
        print(f"{NAMES[name]:22} shown {t['shown']:3} ({10 * t['shown'] / max(1, minutes):.1f}/10 min)  useful {t['useful']:3} "
              f"({100 * t['useful'] / max(1, t['shown']):.0f}%)  late {t['late']:2}  unnecessary {t['unnecessary']:3}  harmful {t['harmful']:2} "
              f"(outside windows {t['outside_harmful']})  invented {t['invented']}"
              + (f"  windows {t['windows']}/{t['windows_total']}  best {t['best']}" if name != "fast" else ""))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["build", "score", "build-v21", "score-v21"])
    parser.add_argument("--runs", required=True)
    parser.add_argument("--set", choices=sorted(SETS))
    parser.add_argument("--pair", default="v21b.json,v21c.json", help="v2.x runs compared per card: first is B, second is C")
    parser.add_argument("--tag", default="v21", help="prefix of the packet, key and verdict files")
    args = parser.parse_args()
    V21["B"], V21["C"] = args.pair.split(",")
    global TAG
    TAG = args.tag
    if args.action == "build-v21":
        return build_v21(Path(args.runs))
    if args.action == "score-v21":
        return score_v21(Path(args.runs))
    (build if args.action == "build" else score)(Path(args.runs), args.set)



# ---------- v2.1: per-card packets without hindsight ----------

V21 = {"B": "v21b.json", "C": "v21c.json"}
TAG = "v21"
AFTER_TURNS, BEFORE_TURNS = 6, 30


def build_v21(runs: Path) -> None:
    """Per call: each card with only the conversation up to it (BEFORE_TURNS turns) and AFTER_TURNS turns after it, labelled
    X/Y at random per call. The judge never sees how the call ended."""
    from evals.strategic.run import context_for

    played = {name: load(runs, [f]) for name, f in V21.items()}
    random.seed(29)
    key = {}
    for cid in SETS["dev"] + SETS["holdout"]:
        call = json.loads((CALLS / f"{cid}.local.json").read_text(encoding="utf-8"))
        turns = call["turns"]
        index = {t["id"]: i for i, t in enumerate(turns)}
        labels = ["X", "Y"]
        random.shuffle(labels)
        key[cid] = dict(zip(V21, labels))
        cards = []
        for name, label in key[cid].items():
            for k, s in enumerate(played[name][cid]["shown"]):
                i = index[s["after_turn"]]
                lines = [f"[{t['id']}] ({int(t['t'] // 60)}:{int(t['t'] % 60):02d}) {'PROSPECT' if t['who'] == 'them' else 'REP'}: {t['text']}"
                         for t in turns[max(0, i - BEFORE_TURNS):i + 1]]
                after = [f"[{t['id']}] {'PROSPECT' if t['who'] == 'them' else 'REP'}: {t['text']}" for t in turns[i + 1:i + 1 + AFTER_TURNS]]
                cards.append({"config": label, "index": k, "appears_after": s["after_turn"], "at": f"{int(s['visible_t'] // 60)}:{int(s['visible_t'] % 60):02d}",
                              "card": f"[{s['kind']}] {s['say']}", "conversation_until_card": "\n".join(lines), "next_turns": "\n".join(after)})
        cards.sort(key=lambda c: index[c["appears_after"]])
        packet = {"company_context": context_for(call), "cards": cards}
        (runs / "exp" / f"{TAG}-in-{cid}.json").write_text(json.dumps(packet, ensure_ascii=False, indent=1), encoding="utf-8")
        print(cid, {n: len(played[n][cid]["shown"]) for n in V21})
    (runs / "exp" / f"key-{TAG}.json").write_text(json.dumps(key, indent=1), encoding="utf-8")


def score_v21(runs: Path) -> None:
    key = json.loads((runs / "exp" / f"key-{TAG}.json").read_text(encoding="utf-8"))
    windows = {}
    for f in WINDOWS:
        if (runs / "exp" / f).exists():
            windows.update(json.loads((runs / "exp" / f).read_text(encoding="utf-8")))
    played = {name: load(runs, [f]) for name, f in V21.items()}
    for which in ("dev", "holdout"):
        tot = {n: {"cards": 0, "useful": 0, "late": 0, "unnecessary": 0, "harmful": 0, "covered": 0, "windows": 0, "minutes": 0.0, "cost": 0.0}
               for n in V21}
        for cid in SETS[which]:
            path = runs / "exp" / f"{TAG}-verdict-{cid}.json"
            if not path.exists():
                print("missing", cid)
                continue
            turns = json.loads((CALLS / f"{cid}.local.json").read_text(encoding="utf-8"))["turns"]
            index = {t["id"]: i for i, t in enumerate(turns)}
            inv = {label: name for name, label in key[cid].items()}
            verdicts = json.loads(path.read_text(encoding="utf-8"))["cards"]
            useful_at = {n: [] for n in V21}
            for v in verdicts:
                n = inv[v["config"]]
                tot[n]["cards"] += 1
                tot[n][v["verdict"]] += 1
                if v["verdict"] == "useful":
                    useful_at[n].append(index[played[n][cid]["shown"][v["index"]]["after_turn"]])
            for n in V21:
                tot[n]["minutes"] += played[n][cid]["duration"] / 60
                tot[n]["cost"] += played[n][cid]["cost"]
                for w in windows.get(cid, []):
                    if "from" not in w:
                        continue
                    tot[n]["windows"] += 1
                    lo, hi = index.get(w["from"], 0), index.get(w["to"], 10**6) + 2
                    tot[n]["covered"] += any(lo <= i <= hi for i in useful_at[n])
        print(f"== {which}")
        for n, t in tot.items():
            m = max(1e-9, t["minutes"])
            print(f"  {V21[n]:15} cards {t['cards']:3} ({10 * t['cards'] / m:.1f}/10 min)  useful {t['useful']:3} "
                  f"({100 * t['useful'] / max(1, t['cards']):.0f}%)  late {t['late']:2}  unnecessary {t['unnecessary']:2}  harmful {t['harmful']:2}  "
                  f"windows {t['covered']}/{t['windows']}  ${30 * t['cost'] / m:.3f} per 30 min")


if __name__ == "__main__":
    main()
