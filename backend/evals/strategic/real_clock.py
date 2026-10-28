"""Give a replayed call its real clock from the live session's own log (live_assist_events), when it ran with live help.

    cd backend && python -m evals.strategic.real_clock 816ba4f7      # writes calls/816ba4f7-real.local.json

Exported memos carry no timings (export_calls synthesises 0.33 s per word). A call made with live help left one row per
moment the prospect finished a thought, with its wall-clock time and their latest words: those are anchors. Each anchor
is matched to the prospect turn whose end it is (by its words, in order); the turns between two anchors share that time
by their word counts. Before the first anchor the synthetic pace is kept. Read-only.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path

from evals.strategic.run import CALLS

MATCH = 0.6  # how alike an event's words and the end of a turn must be to anchor it
SECONDS_PER_WORD = 0.33


def norm(text: str) -> str:
    return " ".join(text.lower().split())


def anchors(turns: list[dict], events: list[dict]) -> list[tuple[int, float]]:
    """[(turn index, seconds since the first anchor's call start)] in order: each event matched to the first prospect turn
    at or after the previous match whose ending looks like the event's words."""
    out, at = [], 0
    for e in events:
        words = norm(e["latest_turn"] or "")
        if len(words.split()) < 3:
            continue
        best = None
        for i in range(at, len(turns)):
            t = turns[i]
            if t["who"] != "them":
                continue
            tail = norm(t["text"])[-len(words):]
            score = SequenceMatcher(None, words, tail).ratio()
            if score >= MATCH:
                best = i
                break
        if best is None:
            continue
        stamp = datetime.fromisoformat(e["created_at"].replace("Z", "+00:00"))
        if out and best == out[-1][0]:
            out[-1] = (best, stamp)  # the same turn checked again later: its end is the later one
        else:
            out.append((best, stamp))
        at = best
    return out


def retime(turns: list[dict], marks: list[tuple[int, datetime]]) -> list[dict]:
    """Turn starts from the anchors (turn ends): a turn's span is proportional to its words between two anchors."""
    weight = [max(1, len(t["text"].split())) for t in turns]
    first_i, first_t = marks[0]
    # Before the first anchor: the synthetic pace, ending at the first anchor.
    lead = sum(weight[: first_i + 1]) * SECONDS_PER_WORD
    origin = first_t - timedelta(seconds=lead)
    ends = [None] * len(turns)
    ends[first_i] = lead
    acc = 0.0
    for k in range(first_i + 1):
        acc += weight[k] * SECONDS_PER_WORD
        ends[k] = acc
    for (i0, t0), (i1, t1) in zip(marks, marks[1:]):
        span = (t1 - t0).total_seconds()
        total = sum(weight[i0 + 1:i1 + 1])
        acc = (t0 - origin).total_seconds()
        for k in range(i0 + 1, i1 + 1):
            acc += span * weight[k] / total
            ends[k] = acc
    last_i = marks[-1][0]
    acc = ends[last_i]
    for k in range(last_i + 1, len(turns)):
        acc += weight[k] * SECONDS_PER_WORD
        ends[k] = acc
    out, start = [], 0.0
    for t, e in zip(turns, ends):
        out.append({**t, "t": round(start, 1)})
        start = e
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("call")
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from evals.copilot.export_calls import supabase

    sb = supabase()
    call = json.loads((CALLS / f"{args.call}.local.json").read_text(encoding="utf-8"))
    memo = sb.table("memos").select("created_at,audio_duration,user_id").eq("id", call["memo_id"]).execute().data[0]
    end = datetime.fromisoformat(memo["created_at"].replace("Z", "+00:00"))
    events = (sb.table("live_assist_events").select("created_at,latest_turn").eq("user_id", memo["user_id"]).eq("kind", "turn")
              .gte("created_at", (end - timedelta(seconds=(memo["audio_duration"] or 0) + 900)).isoformat())
              .lte("created_at", (end + timedelta(minutes=2)).isoformat()).order("created_at").execute().data)
    marks = anchors(call["turns"], events)
    if len(marks) < 5:
        sys.exit(f"only {len(marks)} of {len(events)} events matched a turn: not enough to give the call a real clock")
    turns = retime(call["turns"], marks)
    real = {**call, "id": f"{call['id']}-real", "clock": f"real: {len(marks)} anchors from live_assist_events", "turns": turns}
    path = CALLS / f"{real['id']}.local.json"
    path.write_text(json.dumps(real, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(marks)} of {len(events)} events anchored; synthetic {call['turns'][-1]['t'] / 60:.1f} min → real {turns[-1]['t'] / 60:.1f} min; {path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
