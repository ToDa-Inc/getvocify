"""The gate: what reaches the rep's screen, and when. The producers propose; the gate decides.

    cd backend && python -m evals.strategic.gate --fast fast.json --only ID,ID --out fast-gated.json   # the fast assistant alone

Rules for every card (change them here, nowhere else):
- Never over the other side: a card ready while they are in the middle of saying something waits until they finish it
  (a listening «claro» of the rep does not count as them finishing, see turns.py). An answer that is superseded by a
  newer one before then is not shown.
- An answer the rep has already given is not shown: the rep said REP_ANSWERED_WORDS words of substance since the other
  side finished (production's fast assistant has the same guard when it writes).

Roles when there are two producers (experiment A):
- fast: the immediate answer to what the other side just asked or objected, from an approved source (a playbook answer,
  the offer, the knowledge). A card it builds only from the conversation, a question to go deeper, or a step of the
  playbook (propose a date, ask who decides) is direction: the brain's job, not shown.
- One fast card per reading (the rep can use one); the same approved answer once per call. When it comes back, what to
  do is direction: the brain decides, with the playbook.
- brain: direction (run_v2). It sees in its log every card the rep saw.
With one producer (experiment B) the same rules hold for its answers; its moves go through pending opportunities
(run_v2): show now, keep pending or drop.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from evals.strategic import turns as semantic
from evals.strategic.run import CALLS, SECONDS_PER_WORD, ends, finished_by

FAST_SOURCES = ("objection:", "offer", "knowledge")
FAST_KINDS = {"objection", "question"}
REP_ANSWERED_WORDS = 8


# ---------- for every card ----------


def clear_at(turns: list[dict], t: float) -> float:
    """The first moment from t when the other side is not in the middle of a turn (listening signals of the rep are
    passed over: their idea goes on)."""
    end = ends(turns)
    while True:
        i = semantic.speaking_at(turns, t)
        if i is None:
            return t
        t = end[i]


def speaking_now(turns: list[dict], t: float) -> bool:
    """The other side is in the middle of a turn at second t (listening signals of the rep do not end it)."""
    return semantic.speaking_at(turns, t) is not None


def rep_said(turns: list[dict], after: float, until: float) -> int:
    """Words of substance the rep said between two moments, counting what a turn still in progress has said by then (a
    live transcript arrives word by word); listening signals do not count."""
    signals = semantic.listening(turns)
    total = 0
    for i, u in enumerate(turns):
        if u["who"] != "you" or i in signals or u["t"] < after or u["t"] > until:
            continue
        spoken = u["text"].split()[: max(0, int((until - u["t"]) / SECONDS_PER_WORD))]
        total += semantic.substance(" ".join(spoken))
    return total


def already_answered(turns: list[dict], asked_end: float, at: float) -> bool:
    return rep_said(turns, asked_end, at) >= REP_ANSWERED_WORDS


# ---------- the fast assistant (experiment A) ----------


def fast_candidates(played: dict, turns: list[dict]) -> list[dict]:
    """Every card the fast assistant wrote in a replay, when it was ready, with what it rests on."""
    end = ends(turns)
    out = []
    for r in played["readings"]:
        if r["producer"] != "points" or r.get("reason") == "responder":  # a Responder tap is asked for, not shown on its own
            continue
        ready = end[r["idx"]] + (r.get("model_ms") or 0) / 1000
        for p in r.get("new") or []:
            text = p.get("answer") or p.get("fallback")
            if text:
                out.append({"ready": round(ready, 1), "asked_end": end[r["idx"]], "say": text, "kind": p["kind"],
                            "source": (p.get("source") or {}).get("id") or "", "turns": p.get("turn_ids") or []})
    return out


def fast_role(card: dict) -> str | None:
    """None when the card is the fast assistant's to show; otherwise why it is not."""
    if card["kind"] not in FAST_KINDS:
        return "direction_not_answer"
    if not card["source"].startswith(FAST_SOURCES):
        return "no_approved_source"
    return None


def gate_fast(cards: list[dict], turns: list[dict]) -> tuple[list[dict], list[dict]]:
    """(shown, dropped with why). A shown card has `t`, when it appeared."""
    end = ends(turns)
    cards = sorted(cards, key=lambda c: c["ready"])
    shown, dropped, answered, readings = [], [], set(), set()
    for k, c in enumerate(cards):
        at = clear_at(turns, c["ready"])
        newer = next((n for n in cards[k + 1:] if c["ready"] < n["ready"] <= at and not fast_role(n)), None)
        why = (fast_role(c)
               or ("same_reading" if c["ready"] in readings else None)
               or ("answered_before" if c["source"] in answered else None)
               or ("superseded" if newer else None)
               or ("rep_already_answered" if already_answered(turns, c["asked_end"], at) else None))
        if why:
            dropped.append({**c, "why": why})
            continue
        readings.add(c["ready"])
        answered.add(c["source"])
        shown.append({**c, "t": round(at, 1), "after_turn": turns[max(0, finished_by(end, at) - 1)]["id"]})
    return shown, dropped


def fast_screen(call_ids: list[str], fast_file: str | Path) -> dict:
    """{call id: (shown, dropped)} for the fast assistant's cards in a run_fast replay."""
    out = {}
    for p in json.loads(Path(fast_file).read_text(encoding="utf-8"))["played"]:
        if p["id"] in call_ids:
            turns = json.loads((CALLS / f"{p['id']}.local.json").read_text(encoding="utf-8"))["turns"]
            out[p["id"]] = gate_fast(fast_candidates(p, turns), turns)
    return out


def as_shown(card: dict) -> dict:
    """A fast card in the shape the scorer reads."""
    return {"visible_t": card["t"], "after_turn": card["after_turn"], "say": card["say"], "kind": "fast", "source_quote": "",
            "producer": "fast", "source": card["source"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--fast", required=True, help="a run_fast replay")
    parser.add_argument("--only", required=True, help="comma-separated call ids")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    played = []
    for cid, (shown, dropped) in fast_screen(args.only.split(","), args.fast).items():
        turns = json.loads((CALLS / f"{cid}.local.json").read_text(encoding="utf-8"))["turns"]
        played.append({"id": cid, "shown": [as_shown(c) for c in shown], "dropped": dropped, "duration": ends(turns)[-1], "cost": 0.0})
        why: dict[str, int] = {}
        for d in dropped:
            why[d["why"]] = why.get(d["why"], 0) + 1
        print(f"{cid}: shown {len(shown)}, dropped {len(dropped)} {why}")
    Path(args.out).write_text(json.dumps({"played": played}, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
