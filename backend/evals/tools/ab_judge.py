"""Blind A/B judging of two step-1 outputs (note, tasks, CRM fields) on the same calls.

Usage (from backend/):
  .venv/bin/python evals/tools/ab_judge.py build <out_dir> <crm_grounded_X.json> <crm_grounded_Y.json> [<next_labels.json> ...]
  .venv/bin/python evals/tools/ab_judge.py unblind <out_dir>

`build` writes <out_dir>/ab_1.json and ab_2.json (each call's two versions in random order, with the
labels' crm_note_must_have / crm_must_not), <out_dir>/ab_key.json (which version is X), and exports every
transcript to evals/C04/real/.cache/transcripts/<memo_id>.txt (gitignored: it is customer speech).
Two Sonnet judges then follow evals/judges/JUDGE_CRM_AB.md, one file each, reading the transcript of
each call before judging it, and write <out_dir>/ab_scores_1.json / ab_scores_2.json in input order.
`unblind` prints the totals per system (X, Y) and how often each was preferred.
"""

from __future__ import annotations

import json
import random
import sys
from collections import Counter
from pathlib import Path

CACHE = Path(__file__).resolve().parents[1] / "C04" / "real" / ".cache"
_KEYS = ("summary", "nextSteps", "fields")


def _strip(row: dict) -> dict:
    return {k: row.get(k) for k in _KEYS}


def build(out: Path, x_path: str, y_path: str, label_paths: list[str]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    x = {r["memo_id"]: _strip(r) for r in json.loads(Path(x_path).read_text())}
    y = {r["memo_id"]: _strip(r) for r in json.loads(Path(y_path).read_text())}
    labels = {}
    for path in label_paths:
        for row in json.loads(Path(path).read_text()):
            labels[row["memo_id"]] = row
    memos = json.loads((CACHE / "memos.json").read_text())
    transcripts = CACHE / "transcripts"
    transcripts.mkdir(exist_ok=True)
    rng = random.Random(7)
    items, key = [], {}
    for memo_id in x:
        if memo_id not in y or x[memo_id] == y[memo_id]:
            continue
        (transcripts / f"{memo_id}.txt").write_text(str((memos.get(memo_id) or {}).get("transcript") or ""))
        x_is_a = rng.random() < 0.5
        key[memo_id] = x_is_a
        lab = labels.get(memo_id) or {}
        items.append({
            "memo_id": memo_id,
            "must_have": lab.get("crm_note_must_have") or [],
            "must_not": lab.get("crm_must_not") or [],
            "A": x[memo_id] if x_is_a else y[memo_id],
            "B": y[memo_id] if x_is_a else x[memo_id],
        })
    rng.shuffle(items)
    half = (len(items) + 1) // 2
    (out / "ab_1.json").write_text(json.dumps(items[:half], ensure_ascii=False, indent=1))
    (out / "ab_2.json").write_text(json.dumps(items[half:], ensure_ascii=False, indent=1))
    (out / "ab_key.json").write_text(json.dumps(key))
    print(f"{len(items)} calls -> {out}/ab_1.json ({half}) and ab_2.json ({len(items) - half}); transcripts in {transcripts}")


def unblind(out: Path) -> None:
    key = json.loads((out / "ab_key.json").read_text())
    totals = {"X": Counter(), "Y": Counter()}
    scores = {"X": [], "Y": []}
    better = Counter()
    for n in (1, 2):
        items = json.loads((out / f"ab_{n}.json").read_text())
        judged = json.loads((out / f"ab_scores_{n}.json").read_text())
        assert len(items) == len(judged), f"judge {n}: {len(judged)} scores for {len(items)} calls"
        for item, verdict in zip(items, judged):
            assert item["memo_id"] == verdict["memo_id"], "scores must follow the input order"
            x_is_a = key[item["memo_id"]]
            for system, side in (("X", "A" if x_is_a else "B"), ("Y", "B" if x_is_a else "A")):
                part = verdict[side]
                count = totals[system]
                for value in (part.get("fields") or {}).values():
                    count[value] += 1
                count["missed"] += len(part.get("missed_fields") or [])
                note = part.get("note") or {}
                for k in ("coverage", "invented", "pitch_as_fact", "filler"):
                    count[k] += note.get(k) or 0
                scores[system].append(note.get("score") or 0)
                count["tasks_bad"] += not (part.get("tasks") or {}).get("ok", True)
            pick = verdict.get("better")
            better["same" if pick == "same" else ("X" if (pick == "A") == x_is_a else "Y")] += 1
    for system, count in totals.items():
        bad = count["inferred"] + count["wrong"] + count["trivial"]
        print(f"{system}: fields ok {count['ok']} | inferred+wrong+trivial {bad} | missed {count['missed']} | "
              f"note {sum(scores[system]) / max(1, len(scores[system])):.2f} | coverage {count['coverage']} | "
              f"invented {count['invented']} | pitch_as_fact {count['pitch_as_fact']} | tasks bad {count['tasks_bad']}")
    print("preferred:", dict(better))


if __name__ == "__main__":
    command, out = sys.argv[1], Path(sys.argv[2])
    if command == "build":
        build(out, sys.argv[3], sys.argv[4], sys.argv[5:])
    elif command == "unblind":
        unblind(out)
    else:
        raise SystemExit(__doc__)
