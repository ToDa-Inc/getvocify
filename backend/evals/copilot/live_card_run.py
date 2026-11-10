"""Replay calls through the strategic card (live_card.py, LIVE_CARD_ENABLED) the way the dashboard drives it.

    cd backend && PATH=$HOME/.railway/bin:$PATH python -m evals.copilot.live_card_run --only syn-movertis-06,syn-movertis-14 --json /tmp/card.json

At the end of each prospect turn (4+ words) and each rep turn (12+ words) the card producer is read with the cards already
shown and what the turn check said about their last turn (src/features/desktop/assist/useLiveBrain.ts: read, runCard,
turnObjection). Responder is pressed at the end of a prospect turn a quarter, half and three quarters into the call, as
live_brain_run.py does. Reads the playbook from whatever SUPABASE_URL points at; writes nothing (COPILOT_LOG_EVENTS off).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

MS_PER_WORD = 0.33  # seconds a word takes to say, as synthetic_calls.py times the turns

from evals.copilot.live_brain_run import (
    CALLS, MIN_PROSPECT_WORDS, MIN_REP_WORDS, client_for, load_production_provider, sse_frames, window_of, words,
)


def _objection(turns: list[dict], ctx) -> str | None:
    """The turn check on their last turn with the playbook's own objections, as the island gets it (turnObjection)."""
    from app.services.copilot import turn as turn_check
    from app.services.copilot.playbook_objections import custom_entries

    conversation = "\n".join(f"{'Them' if t['who'] == 'them' else 'You'}: {t['text']}" for t in turns[-12:])
    reading = asyncio.run(turn_check.read_turn(conversation, turns[-1]["text"], custom_entries(ctx.snapshot) or None))
    if not reading.get("objection"):
        return None
    return reading.get("entry_id") if reading["objection"] == "custom" else reading["objection"]


def play(call: dict) -> dict:
    client, sb, membership, api = client_for(call)
    from app.services.copilot.live_models import LiveReading

    turns = call["turns"]
    stub = LiveReading(call_id=call["id"], sales_motion_key=call["motion"], call_mode=call["call_mode"], turns=turns[:1])
    ctx = asyncio.run(api._brain_context(sb, membership, stub))
    cards: list[dict] = []
    readings: list[dict] = []
    last_read_t = None
    version = 0

    def reading(idx: int, reason: str, objection: str | None = None):
        nonlocal last_read_t, version
        upto = turns[: idx + 1]
        now_t = upto[-1]["t"] + words(upto[-1]["text"]) * MS_PER_WORD
        body = {
            "call_id": call["id"], "sales_motion_key": call["motion"], "call_mode": call["call_mode"], "language": "es",
            "say_view": True, "reason": reason, "turns": window_of(upto), "state_version": version, "type_changed": False,
            "cards": [{k: c[k] for k in ("id", "say", "visible_t", "open")} for c in cards],
            **({"objection": objection[:200]} if objection else {}),
            **({"last_read_t": last_read_t} if last_read_t is not None else {}), "now_t": round(now_t, 1),
        }
        t0 = time.perf_counter()
        response = client.post("/api/v1/copilot/live/card", json=body)
        wall = int((time.perf_counter() - t0) * 1000)
        result = response.json() if response.status_code == 200 else {"error": f"HTTP {response.status_code}: {response.text[:200]}"}
        if "type" not in result and response.headers.get("content-type", "").startswith("text/event-stream"):
            result = next((f for f in reversed(sse_frames(response.text)) if f["type"] == "result"), {})
        version += 1
        if isinstance(result.get("read_t"), (int, float)) and not str(result.get("event", "")).startswith("skipped"):
            last_read_t = result["read_t"]
        closed = {c.get("id") if isinstance(c, dict) else c for c in result.get("closed") or []}
        for c in cards:
            if c["id"] in closed:
                c["open"] = False
        new = []
        for p in result.get("points") or []:
            for c in cards:
                c["open"] = False  # one card on screen: the new one replaces it
            say = p.get("answer") or p.get("fallback") or ""
            card = {"id": p["id"], "say": say[:400], "visible_t": float(result.get("read_t") or now_t), "open": True,
                    "turn": upto[-1]["id"], "reason": reason, "kind": p.get("kind"), "source": (p.get("source") or {}).get("label")}
            cards.append(card)
            new.append(card)
        readings.append({"turn": upto[-1]["id"], "idx": idx, "reason": reason, "objection": objection, "wall_ms": wall,
                         "event": result.get("event"), "moment": result.get("moment"), "model": result.get("model"),
                         "error": result.get("error"), "new": new})

    ends = [i for i, t in enumerate(turns) if t["who"] == "them" and words(t["text"]) >= MIN_PROSPECT_WORDS
            and (i + 1 >= len(turns) or turns[i + 1]["who"] != "them")]
    taps = {ends[int(len(ends) * q)] for q in (0.25, 0.5, 0.75)} if ends else set()
    for i, turn in enumerate(turns):
        if not (i + 1 >= len(turns) or turns[i + 1]["who"] != turn["who"]):
            continue
        if turn["who"] == "them" and words(turn["text"]) >= MIN_PROSPECT_WORDS:
            reading(i, "turn_end", _objection(turns[: i + 1], ctx))
            if i in taps:
                reading(i, "responder")
        elif turn["who"] == "you" and words(turn["text"]) >= MIN_REP_WORDS:
            reading(i, "rep_turn")
    return {"id": call["id"], "playbook_version_id": ctx.playbook_version_id, "readings": readings, "cards": cards}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--only", required=True, help="comma-separated call ids")
    parser.add_argument("--json", required=True, help="write the readings and cards here (keep it out of the repository)")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    # Production's model path: direct Together, OpenRouter only as its backup (needs the railway CLI on PATH).
    load_production_provider()
    from app.services.copilot.suggest import live_direct

    if not live_direct():
        raise SystemExit("the direct provider (Together) is not configured: put the railway CLI on PATH")
    calls = [json.loads((CALLS / f"{cid}.local.json").read_text(encoding="utf-8")) for cid in args.only.split(",")]
    with ThreadPoolExecutor(args.workers) as pool:
        played = list(pool.map(play, calls))
    Path(args.json).write_text(json.dumps({"played": played}, ensure_ascii=False, indent=1), encoding="utf-8")
    for p in played:
        errors = sum(1 for r in p["readings"] if r["error"])
        print(f"{p['id']}: {len(p['readings'])} readings, {len(p['cards'])} cards, {errors} errors, playbook {p['playbook_version_id'][:8]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
