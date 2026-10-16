"""A sheet for a person to set the labels of the live call assistant's decisions, from a run's --json output.

    python -m evals.copilot.label_sheet run.json > sheet.md        # customer speech: keep it out of the repository

For each call: every point the brain wrote (what they said, its decision, the line) and, between them, the other things the
other side said, so the moments the brain stayed silent on can be labelled "none". A label is
{"call", "said": a few words of what they said (matched to the turn), "expect": {"decision": responder|reconducir|aplazar|cerrar|null|none},
"confirmed": true once a person set it} in labels.json; `decision: "none"` means no point should come from that turn,
`null` means a point with no decision (only the answer).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

CALLS = Path(__file__).with_name("calls")


def main() -> None:
    run = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    for played in run["played"]:
        call = json.loads((CALLS / f"{played['id']}.local.json").read_text(encoding="utf-8"))
        points = {t: p for p in played["state"]["points"] for t in p["turn_ids"][:1]}
        print(f"\n## {played['id']} — {call['motion']} ({len(call['turns'])} turns)\n")
        for turn in call["turns"]:
            if turn["who"] != "them":
                continue
            point = points.get(turn["id"])
            text = turn["text"][:200]
            if point:
                say = point.get("answer") or point.get("fallback") or ""
                print(f"- **{turn['id']}** «{text}»\n  - brain: {point['kind']}/{point['tag_key']} · decision {point['decision']} · {point['outcome']}"
                      f"{' · ' + point['decision_note'] if point.get('decision_note') else ''}\n  - says: {say}\n  - label: ")
            elif len(turn["text"].split()) >= 8:
                print(f"- {turn['id']} «{text}» — no point")


if __name__ == "__main__":
    main()
